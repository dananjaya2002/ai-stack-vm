import os
import json
import time
import sys
from pathlib import Path
from collections import OrderedDict
from typing import Any, Dict, List, Optional

import requests
from fastapi import FastAPI
from pydantic import BaseModel
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer
from functools import lru_cache


sys.path.append(str(Path(__file__).resolve().parents[1]))
from proxy_security import install_security_middleware, validate_proxy_environment
from shared.json_log import append_json_event
from shared.utility_prompts import classify_utility_prompt, utility_prompt_content


app = FastAPI(title="Code Proxy API")

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
try:
    QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
except ValueError:
    print("code-proxy configuration error:\n- QDRANT_PORT must be an integer", file=sys.stderr)
    raise SystemExit(1)
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "code-memory")

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:8082/v1").rstrip("/")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen2.5-coder-7b-instruct-q4_k_m.gguf")

CODE_TOP_K = int(os.getenv("CODE_TOP_K", "8"))
CODE_SCORE_THRESHOLD = float(os.getenv("CODE_SCORE_THRESHOLD", "0.35"))

EMBED_MODEL_NAME = os.getenv("EMBED_MODEL_NAME", "all-MiniLM-L6-v2")

ENABLE_LOGGING = os.getenv("CODE_PROXY_LOGS", "false").lower() == "true"
SKIP_UTILITY_PROMPTS = os.getenv("SKIP_UTILITY_PROMPTS", "true").lower() == "true"
LOG_FILE = Path(os.getenv("CODE_PROXY_LOG_FILE", "/tmp/code_proxy.log"))

SEARCH_LIMIT_MULTIPLIER = int(os.getenv("SEARCH_LIMIT_MULTIPLIER", "5"))
MAX_CHUNKS_PER_FILE = int(os.getenv("MAX_CHUNKS_PER_FILE", "2"))
MAX_CONTEXT_CHARS = int(os.getenv("MAX_CONTEXT_CHARS", "45000"))
MAX_CHUNK_CHARS = int(os.getenv("MAX_CHUNK_CHARS", "4000"))
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
embedder = SentenceTransformer(EMBED_MODEL_NAME)


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


        item = {
            "score": original_score,
            "boosted_score": boosted_score,
            "repo": payload.get("repo"),
            "relative_path": relative_path,
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
    return f"""
You are a private repo-aware coding agent running inside VS Code through Continue.dev.

You have access to retrieved project code chunks from Qdrant.


Rules:
- Use the retrieved code context first.
- Use Symbol Type and Symbol Name to identify relevant functions, classes, components, routes, or documentation sections.
- Do not invent files, functions, APIs, or project structure.
- If context is insufficient, clearly say what extra file or context is needed.
- Prefer minimal, safe, maintainable code changes.
- For implementation tasks, provide a short plan before code.
- For debugging tasks, explain likely cause and verification command.
- Mention affected files when possible.
- If you suggest commands, keep them specific.
- If multiple files are involved, explain how they connect.

Retrieved code context:

{code_context}

User request:

{user_question}
""".strip()


def call_llm(prompt: str, temperature: float = 0.2, max_tokens: int = 2048) -> Dict[str, Any]:
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "You are a precise, practical coding assistant.",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }

    response = requests.post(
        f"{LLM_BASE_URL}/chat/completions",
        json=payload,
        timeout=300,
    )

    response.raise_for_status()
    return response.json()


@lru_cache(maxsize=256)
def embed_query_cached(query: str):
    return embedder.encode(query).tolist()

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
    answer = call_llm(prompt)

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
        return {
            "id": "code-proxy-utility",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": "code-proxy",
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": utility_prompt_content(utility_prompt_type)},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }

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
    )

    return llm_response
