import os
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from fastapi import FastAPI
from pydantic import BaseModel
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer


app = FastAPI(title="Code Proxy API")

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "code-memory")

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:8082/v1").rstrip("/")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen2.5-coder-7b-instruct-q4_k_m.gguf")

CODE_TOP_K = int(os.getenv("CODE_TOP_K", "8"))
CODE_SCORE_THRESHOLD = float(os.getenv("CODE_SCORE_THRESHOLD", "0.35"))

EMBED_MODEL_NAME = os.getenv("EMBED_MODEL_NAME", "all-MiniLM-L6-v2")

ENABLE_LOGGING = os.getenv("CODE_PROXY_LOGS", "false").lower() == "true"
LOG_FILE = Path(os.getenv("CODE_PROXY_LOG_FILE", "/tmp/code_proxy.log"))

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

    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

        entry = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "event": event,
            "data": data,
        }

        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    except Exception as e:
        print(f"⚠️ Logging failed: {e}")


def latest_user_message(messages: List[ChatMessage]) -> str:
    for msg in reversed(messages):
        if msg.role == "user":
            return msg.content
    return ""


def search_code(query: str, repo: Optional[str] = None) -> List[Dict[str, Any]]:
    vector = embedder.encode(query).tolist()

    results = client.query_points(
        collection_name=QDRANT_COLLECTION,
        query=vector,
        limit=CODE_TOP_K,
    )

    selected = []

    for result in results.points:
        if result.score < CODE_SCORE_THRESHOLD:
            continue

        payload = result.payload or {}

        if repo and payload.get("repo") != repo:
            continue

        selected.append(
            {
                "score": result.score,
                "repo": payload.get("repo"),
                "relative_path": payload.get("relative_path"),
                "language": payload.get("language"),
                "chunk_index": payload.get("chunk_index"),
                "text": payload.get("text"),
            }
        )

    log_event(
        "search_code",
        {
            "query": query,
            "repo": repo,
            "selected_count": len(selected),
            "selected": [
                {
                    "score": x["score"],
                    "repo": x["repo"],
                    "relative_path": x["relative_path"],
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

    for item in chunks:
        header = (
            f"Repo: {item.get('repo')}\n"
            f"File: {item.get('relative_path')}\n"
            f"Language: {item.get('language')}\n"
            f"Chunk: {item.get('chunk_index')}\n"
            f"Score: {item.get('score')}\n"
        )

        parts.append(
            "----- CODE CONTEXT START -----\n"
            + header
            + "\n"
            + (item.get("text") or "")
            + "\n----- CODE CONTEXT END -----"
        )

    return "\n\n".join(parts)


def build_prompt(user_question: str, code_context: str) -> str:
    return f"""
You are a private repo-aware coding agent running inside VS Code through Continue.dev.

You have access to retrieved project code chunks from Qdrant.

Rules:
- Use the retrieved code context first.
- Do not invent files, functions, APIs, or project structure.
- If context is insufficient, clearly say what extra file or context is needed.
- Prefer minimal, safe, maintainable code changes.
- For implementation tasks, provide a short plan before code.
- For debugging tasks, explain the likely cause and verification command.
- Mention affected files when possible.
- If you suggest commands, keep them specific.

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
