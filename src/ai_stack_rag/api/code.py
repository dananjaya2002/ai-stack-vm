"""Code RAG FastAPI application."""

import os
import sys
import time
from pathlib import Path
from collections import OrderedDict
from typing import Any, Dict, List, Optional

from fastapi import FastAPI
from pydantic import BaseModel
from qdrant_client import QdrantClient
from ai_stack_rag.embeddings.provider import EmbeddingProvider
from functools import lru_cache


from ai_stack_rag.llm.openai_compat import proxy_completion, upstream_payload
from ai_stack_rag.prompts.utility import classify_utility_prompt
from ai_stack_rag.prompts.templates import code_rag_prompt
from ai_stack_rag.utils.json_log import append_json_event
from ai_stack_rag.utils.security import install_security_middleware, validate_proxy_environment
from ai_stack_rag.utils.source_locations import (
    canonical_source_path,
    clean_source_markers,
    format_source_location,
)
from ai_stack_rag.utils.config import load_settings

SETTINGS = load_settings()

app = FastAPI(title="Code Proxy API")


def create_app() -> FastAPI:
    """Return the configured code API application."""
    return app

QDRANT_HOST = os.getenv("QDRANT_HOST", SETTINGS.vector_db.host)
try:
    QDRANT_PORT = int(os.getenv("QDRANT_PORT", str(SETTINGS.vector_db.port)))
except ValueError:
    print("code-proxy configuration error:\n- QDRANT_PORT must be an integer", file=sys.stderr)
    raise SystemExit(1)
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", SETTINGS.vector_db.code_collection)

LLM_BASE_URL = os.getenv("LLM_BASE_URL", SETTINGS.llm.base_url).rstrip("/")
LLM_MODEL = os.getenv("LLM_MODEL", SETTINGS.llm.model)

CODE_TOP_K = int(os.getenv("CODE_TOP_K", "8"))
CODE_SCORE_THRESHOLD = float(os.getenv("CODE_SCORE_THRESHOLD", "0.35"))

EMBED_MODEL_NAME = os.getenv("EMBED_MODEL_NAME", SETTINGS.embeddings.model)

ENABLE_LOGGING = os.getenv("CODE_PROXY_LOGS", "false").lower() == "true"
SKIP_UTILITY_PROMPTS = os.getenv("SKIP_UTILITY_PROMPTS", "true").lower() == "true"
LOG_FILE = Path(os.getenv("CODE_PROXY_LOG_FILE", SETTINGS.logging.code_file))

SEARCH_LIMIT_MULTIPLIER = int(os.getenv("SEARCH_LIMIT_MULTIPLIER", "5"))
MAX_CHUNKS_PER_FILE = int(os.getenv("MAX_CHUNKS_PER_FILE", str(SETTINGS.retrieval.max_chunks_per_file)))
MAX_CONTEXT_CHARS = int(os.getenv("MAX_CONTEXT_CHARS", str(SETTINGS.retrieval.max_context_chars)))
MAX_CHUNK_CHARS = int(os.getenv("MAX_CHUNK_CHARS", str(SETTINGS.retrieval.max_chunk_chars)))
REPOS_ROOT = Path(
    os.getenv(
        "REPOS_ROOT",
        str(Path.home() / "ai-stack" / "memory" / "code-memory"),
    )
)

validate_proxy_environment(
    "code-proxy",
    required_vars=[
        "LLM_BASE_URL",
        "LLM_MODEL",
        "QDRANT_HOST",
        "QDRANT_PORT",
        "QDRANT_COLLECTION",
        "REPOS_ROOT",
    ],
    required_paths=[str(REPOS_ROOT)],
)

install_security_middleware(app, "code-proxy")

client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
embedder = EmbeddingProvider(EMBED_MODEL_NAME)


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: Optional[str] = "code-proxy"
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.2
    max_tokens: Optional[int] = 2048
    stream: Optional[bool] = False


class AskRequest(BaseModel):
    question: str
    repo: Optional[str] = None


def log_event(event: str, data: Dict[str, Any]):
    if not ENABLE_LOGGING:
        return

    entry = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "event": event,
        "data": data,
    }
    error = append_json_event(LOG_FILE, entry)
    if error:
        print(f"Logging failed: {error}", file=sys.stderr)

log_event("proxy_started", {"service": "code-proxy"})


def latest_user_message(messages: List[ChatMessage]) -> str:
    for msg in reversed(messages):
        if msg.role == "user":
            return msg.content
    return ""
def expand_query(query: str) -> str:
    q = query.lower()
    extra_terms = []

    if "video" in q or "stream" in q:
        extra_terms.extend([
            "streaming",
            "video player",
            "media",
            "assets",
            "thumbnail",
            "upload",
            "frontend",
            "backend",
            "api",
        ])

    if "auth" in q or "login" in q:
        extra_terms.extend([
            "authentication",
            "authorization",
            "token",
            "session",
            "middleware",
            "user",
        ])

    if "docker" in q or "container" in q:
        extra_terms.extend([
            "Dockerfile",
            "docker-compose",
            "container",
            "service",
            "port",
            "volume",
        ])

    if "api" in q:
        extra_terms.extend([
            "endpoint",
            "route",
            "request",
            "response",
            "server",
            "client",
        ])

    if not extra_terms:
        return query

    return query + "\nRelated code search terms: " + ", ".join(sorted(set(extra_terms)))

def boost_score(score: float, payload: Dict[str, Any], query: str) -> float:
    boosted = float(score)
    q = query.lower()

    path = (payload.get("relative_path") or "").lower()
    language = (payload.get("language") or "").lower()
    text = (payload.get("text") or "").lower()
    category = (payload.get("category") or "").lower()
    symbol_type = (payload.get("symbol_type") or "").lower()
    symbol_name = (payload.get("symbol_name") or "").lower()

    if "frontend" in q and "frontend" in path:
        boosted += 0.08

    if "backend" in q and "backend" in path:
        boosted += 0.08

    if "api" in q and ("api" in path or "api" in text or "endpoint" in text or "route" in text):
        boosted += 0.05

    if ("video" in q or "stream" in q) and (
        "video" in path or "stream" in path or "video" in text or "stream" in text
    ):
        boosted += 0.08

    if "react" in q and language in {
        "tsx",
        "jsx",
        "typescript",
        "javascript",
        "typescriptreact",
        "javascriptreact",
    }:
        boosted += 0.05

    if "docker" in q and ("docker" in path or "docker" in text or language == "dockerfile"):
        boosted += 0.10

    # New symbol-aware boosts
    if symbol_name and symbol_name in q:
        boosted += 0.15

    if any(x in q for x in ["component", "ui", "panel", "page", "screen"]):
        if symbol_type == "react_component":
            boosted += 0.10

    if any(x in q for x in ["function", "method", "handler", "route", "endpoint"]):
        if symbol_type in {"function", "async_function", "arrow_function", "fastapi_route", "method"}:
            boosted += 0.08

    if any(x in q for x in ["class", "service", "manager", "controller"]):
        if symbol_type in {"class", "interface", "struct"}:
            boosted += 0.06

    if any(x in q for x in ["docs", "readme", "protocol", "architecture", "guide"]):
        if category == "docs" or symbol_type == "markdown_section":
            boosted += 0.08

    if any(x in q for x in ["config", "env", "compose", "yaml", "settings"]):
        if category == "config":
            boosted += 0.08

    return boosted


def search_code(query: str, repo: Optional[str] = None) -> List[Dict[str, Any]]:
    expanded_query = expand_query(query)
    vector = embed_query_cached(expanded_query)


    limit = max(CODE_TOP_K * SEARCH_LIMIT_MULTIPLIER, CODE_TOP_K)

    results = client.query_points(
        collection_name=QDRANT_COLLECTION,
        query=vector,
        limit=limit,
        with_payload=True,
        with_vectors=False,
    )

    file_chunks = OrderedDict()

    for result in results.points:
        payload = result.payload or {}
        original_score = float(result.score)
        boosted_score = boost_score(original_score, payload, query)

        if boosted_score < CODE_SCORE_THRESHOLD:
            continue

        if repo and payload.get("repo") != repo:
            continue

        relative_path = payload.get("relative_path") or payload.get("file") or "unknown"
        source_path = canonical_source_path(
            "code",
            repo_name=payload.get("repo"),
            relative_path=relative_path,
            file_path=payload.get("file"),
            source_path=payload.get("source_path"),
        )
        source_location = format_source_location(
            "code",
            repo_name=payload.get("repo"),
            source_path=source_path,
            line_start=payload.get("line_start"),
            line_end=payload.get("line_end"),
            chunk_index=payload.get("chunk_index"),
        )


        item = {
            "score": original_score,
            "boosted_score": boosted_score,
            "repo": payload.get("repo"),
            "relative_path": relative_path,
            "source_path": source_path,
            "source_location": source_location,
            "line_start": payload.get("line_start"),
            "line_end": payload.get("line_end"),
            "language": payload.get("language"),
            "category": payload.get("category", "code"),
            "symbol_type": payload.get("symbol_type", "text_chunk"),
            "symbol_name": payload.get("symbol_name"),
            "symbol_subchunk_index": payload.get("symbol_subchunk_index", 0),
            "chunk_index": payload.get("chunk_index"),
            "text": payload.get("text"),
        }


        if relative_path not in file_chunks:
            file_chunks[relative_path] = []

        file_chunks[relative_path].append(item)

    selected = []

    for relative_path, chunks in file_chunks.items():
        chunks = sorted(chunks, key=lambda x: x["boosted_score"], reverse=True)

        for item in chunks[:MAX_CHUNKS_PER_FILE]:
            selected.append(item)

            if len(selected) >= CODE_TOP_K:
                break

        if len(selected) >= CODE_TOP_K:
            break

    log_event(
        "search_code",
        {
            "query": query,
            "expanded_query": expanded_query,
            "repo": repo,
            "raw_count": len(results.points),
            "selected_count": len(selected),            
            "selected": [
                {
                    "score": x["score"],
                    "boosted_score": x["boosted_score"],
                    "repo": x["repo"],
                    "relative_path": x["relative_path"],
                    "source_path": x["source_path"],
                    "line_start": x.get("line_start"),
                    "line_end": x.get("line_end"),
                    "language": x.get("language"),
                    "category": x.get("category"),
                    "symbol_type": x.get("symbol_type"),
                    "symbol_name": x.get("symbol_name"),
                    "symbol_subchunk_index": x.get("symbol_subchunk_index"),
                    "chunk_index": x["chunk_index"],
                }
                for x in selected
            ],
        },
    )

    return selected


def build_code_context(chunks: List[Dict[str, Any]]) -> str:
    if not chunks:
        return "No relevant indexed code chunks were found."

    parts = []
    total_chars = 0

    for item in chunks:
        text = item.get("text") or ""
        text = text[:MAX_CHUNK_CHARS]

        block = f"""
[CODE CHUNK]
Repo: {item.get("repo")}
File: {item.get("relative_path")}
Location: {item.get("source_location")}
Language: {item.get("language")}
Category: {item.get("category")}
Symbol Type: {item.get("symbol_type")}
Symbol Name: {item.get("symbol_name")}
Symbol Subchunk: {item.get("symbol_subchunk_index")}
Chunk: {item.get("chunk_index")}
Score: {round(float(item.get("score") or 0), 4)}
Boosted Score: {round(float(item.get("boosted_score") or 0), 4)}

{text}
[/CODE CHUNK]
""".strip()

        if total_chars + len(block) > MAX_CONTEXT_CHARS:
            break

        parts.append(block)
        total_chars += len(block)

    return "\n\n".join(parts)

def build_prompt(user_question: str, code_context: str) -> str:
    return code_rag_prompt(user_question, code_context)


def call_llm(
    prompt: str,
    temperature: float = 0.2,
    max_tokens: int = 2048,
    stream: bool = False,
    source_locations: Optional[List[str]] = None,
) -> Any:
    payload = upstream_payload(
        LLM_MODEL,
        [
            {
                "role": "system",
                "content": "You are a precise, practical coding assistant.",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        temperature,
        max_tokens,
        stream,
    )
    return proxy_completion(
        f"{LLM_BASE_URL}/chat/completions",
        payload,
        "code-proxy",
        "code-proxy",
        stream,
        content_transform=(
            lambda content: clean_source_markers(content, source_locations or [])
        ),
    )


@lru_cache(maxsize=256)
def embed_query_cached(query: str):
    return embedder.encode(query)

@app.get("/v1/models")
def models():
    return {
        "object": "list",
        "data": [
            {
                "id": "code-proxy",
                "object": "model",
                "owned_by": "local",
            }
        ],
    }


@app.post("/search")
def search_endpoint(req: AskRequest):
    return {
        "results": search_code(req.question, repo=req.repo)
    }


@app.post("/ask")
def ask(req: AskRequest):
    chunks = search_code(req.question, repo=req.repo)
    context = build_code_context(chunks)
    prompt = build_prompt(req.question, context)
    answer = call_llm(
        prompt,
        source_locations=[chunk["source_location"] for chunk in chunks],
    )

    return {
        "question": req.question,
        "repo": req.repo,
        "chunks": chunks,
        "answer": answer,
    }


@app.post("/v1/chat/completions")
def chat_completions(req: ChatCompletionRequest):
    user_question = latest_user_message(req.messages)
    utility_prompt_type = classify_utility_prompt(user_question) if SKIP_UTILITY_PROMPTS else None
    if utility_prompt_type:
        log_event("utility_prompt_skipped", {"utility_prompt_type": utility_prompt_type})
        payload = upstream_payload(
            LLM_MODEL,
            [{"role": message.role, "content": message.content} for message in req.messages],
            req.temperature or 0.2,
            req.max_tokens or 2048,
            bool(req.stream),
        )
        return proxy_completion(
            f"{LLM_BASE_URL}/chat/completions",
            payload,
            "code-proxy",
            "code-proxy-utility",
            bool(req.stream),
        )

    chunks = search_code(user_question)
    context = build_code_context(chunks)
    prompt = build_prompt(user_question, context)

    log_event(
        "prompt_built",
        {
            "user_question": user_question,
            "context_chars": len(context),
        },
    )

    llm_response = call_llm(
        prompt,
        temperature=req.temperature or 0.2,
        max_tokens=req.max_tokens or 2048,
        stream=bool(req.stream),
        source_locations=[chunk["source_location"] for chunk in chunks],
    )

    return llm_response
