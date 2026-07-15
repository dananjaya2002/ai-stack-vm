import sys
from fastapi import FastAPI
from pydantic import BaseModel

from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

import os
import time
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))
from proxy_security import install_security_middleware, validate_proxy_environment
from shared.json_log import append_json_event
from shared.openai_compat import proxy_completion, upstream_payload
from shared.utility_prompts import classify_utility_prompt

LOG_FILE = Path(os.getenv("MEMORY_API_LOG_FILE", "/tmp/memory_api.log"))
ENABLE_LOGGING = os.getenv("MEMORY_API_LOGS", "true").lower() == "true"
SKIP_UTILITY_PROMPTS = os.getenv("SKIP_UTILITY_PROMPTS", "true").lower() == "true"


# CONFIG
MEMORY_DIR = os.getenv("MEMORY_DIR", "/memory")
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
try:
    QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
except ValueError:
    print("memory-proxy configuration error:\n- QDRANT_PORT must be an integer", file=sys.stderr)
    raise SystemExit(1)
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "engineering-memory")

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:8082/v1")
LLAMA_API = f"{LLM_BASE_URL.rstrip('/')}/chat/completions"
MODEL_NAME = os.getenv("LLM_MODEL", "qwen2.5-coder-7b-instruct-q4_k_m.gguf")

TOP_K = int(os.getenv("MEMORY_TOP_K", "5"))
SCORE_THRESHOLD = float(os.getenv("MEMORY_SCORE_THRESHOLD", "0.25"))


validate_proxy_environment(
    "memory-proxy",
    required_vars=[
        "LLM_BASE_URL",
        "LLM_MODEL",
        "QDRANT_HOST",
        "QDRANT_PORT",
        "QDRANT_COLLECTION",
    ],
    required_paths=[MEMORY_DIR],
)

app = FastAPI()
install_security_middleware(app, "memory-proxy")

# INIT
client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
embed_model = SentenceTransformer("all-MiniLM-L6-v2")


# -----------------------------
# REQUEST MODELS
# -----------------------------
class QueryRequest(BaseModel):
    query: str


# -----------------------------
# ✅ SMART MEMORY SEARCH
# -----------------------------
def search_memory(query):
    try:
        # ✅ Added query initiation log
        log_event({
            "type": "search_query",
            "query": query
        })

        vector = embed_model.encode(query).tolist()

        results = client.query_points(
            collection_name=COLLECTION_NAME,
            query=vector,
            limit=TOP_K * 4  # ✅ fetch extra for filtering
        )

        contexts = []
        file_chunks = {}   # ✅ store multiple chunks per file

        for r in results.points:
            payload = r.payload or {}

            text = payload.get("text", "")
            file = payload.get("file", "")
            category = payload.get("category", "unknown")

            
            log_event({
                "type": "chunk_seen",
                "file": file,
                "score": r.score
            })

            # ✅ relevance filter
            if r.score < SCORE_THRESHOLD:
                continue

            # ✅ category filtering (optional)
            if "debug" in query.lower() and category != "debugging":
                continue
            if "persona" in query.lower() and category != "persons":
                continue

            # ✅ Added chunk selection log (after filter pass)
            log_event({
                "type": "chunk_selected",
                "file": file,
                "category": category,
                "score": r.score,
                "preview": text[:120]
            })

            if file not in file_chunks:
                file_chunks[file] = []

            # ✅ collect chunks per file
            file_chunks[file].append((r.score, text))

        # ✅ pick top 2 chunks per file
        for file, chunks in file_chunks.items():
            chunks = sorted(chunks, key=lambda x: x[0], reverse=True)

            for score, text in chunks[:2]:
                contexts.append(text)

            if len(contexts) >= TOP_K:
                break

        # ✅ limit final contexts
        final_contexts = contexts[:TOP_K]

        # ✅ NEW: log final context summary
        log_event({
            "type": "final_context",
            "query": query,
            "contexts_count": len(final_contexts),
            "note": "multi-chunk applied"
        })
        
        return final_contexts

    except Exception as e:
        print(f"⚠️ Memory search failed: {e}")
        return []


# -----------------------------
# ✅ PROMPT BUILDER
# -----------------------------
def build_prompt(query, contexts):
    if contexts:
        context_text = "\n\n".join(contexts)

        return f"""
You are a senior software engineering assistant.

Use the memory context below ONLY if it is relevant.

================ MEMORY =================
{context_text}
=========================================

QUESTION:
{query}

INSTRUCTIONS:
- Be clear and structured
- Use memory when relevant
- Ignore irrelevant memory
"""
    else:
        return f"""
QUESTION:
{query}

Answer clearly and practically.
"""


# -----------------------------
# MODEL CALL
# -----------------------------
def query_model(prompt, stream=False):
    try:
        payload = upstream_payload(
            MODEL_NAME,
            [{"role": "user", "content": prompt}],
            0.2,
            2048,
            stream,
        )
        result = proxy_completion(
            LLAMA_API,
            payload,
            "memory-proxy",
            "memory-proxy",
            stream,
            timeout=300,
        )
        if stream:
            return result
        return result["choices"][0]["message"]["content"]

    except Exception as e:
        return f"⚠️ Model error: {e}"

# -----------------------------
# log event
# -----------------------------

def log_event(data):
    if not ENABLE_LOGGING:
        return

    entry = {"timestamp": time.strftime("%Y-%m-%d %H:%M:%S"), **data}
    error = append_json_event(LOG_FILE, entry)
    if error:
        print(f"Memory logging failed: {error}", file=sys.stderr)


log_event({"type": "proxy_started", "service": "memory-proxy"})



# -----------------------------
# BASIC ENDPOINTS
# -----------------------------
@app.post("/ask")
def ask(req: QueryRequest):
    contexts = search_memory(req.query)
    prompt = build_prompt(req.query, contexts)
    answer = query_model(prompt)

    return {
        "query": req.query,
        "answer": answer,
        "context_used": contexts
    }


@app.post("/search")
def search(req: QueryRequest):
    return {
        "results": search_memory(req.query)
    }


# -----------------------------
# ✅ OPENAI COMPATIBLE ENDPOINTS
# -----------------------------
@app.get("/v1/models")
def list_models():
    return {
        "object": "list",
        "data": [
            {
                "id": "memory-proxy",
                "object": "model",
                "owned_by": "local",
            }
        ]
    }


@app.post("/v1/chat/completions")
def openai_chat(req: dict):
    try:
        messages = req.get("messages", [])

        user_msg = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_msg = msg.get("content", "")
                break

        if not user_msg:
            return {"error": "No user message found"}

        utility_prompt_type = classify_utility_prompt(user_msg) if SKIP_UTILITY_PROMPTS else None
        if utility_prompt_type:
            log_event({
                "type": "utility_prompt_skipped",
                "utility_prompt_type": utility_prompt_type,
            })
            stream = bool(req.get("stream", False))
            payload = upstream_payload(
                MODEL_NAME,
                messages,
                float(req.get("temperature", 0.2)),
                int(req.get("max_tokens", 2048)),
                stream,
            )
            return proxy_completion(
                LLAMA_API,
                payload,
                "memory-proxy",
                "memory-proxy-utility",
                stream,
            )

        contexts = search_memory(user_msg)
        prompt = build_prompt(user_msg, contexts)

        # ✅ Added pre-inference log
        log_event({
            "type": "prompt_built",
            "query": user_msg,
            "context_size": len(contexts)
        })

        stream = bool(req.get("stream", False))
        if stream:
            payload = upstream_payload(
                MODEL_NAME,
                [{"role": "user", "content": prompt}],
                float(req.get("temperature", 0.2)),
                int(req.get("max_tokens", 2048)),
                True,
            )
            return proxy_completion(
                LLAMA_API,
                payload,
                "memory-proxy",
                "memory-proxy",
                True,
            )

        answer = query_model(prompt)

        # ✅ Added post-inference response log
        log_event({
            "type": "model_response",
            "query": user_msg,
            "response_preview": answer[:200]
        })

        return {
            "id": "memory_api",
            "object": "chat.completion",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": answer
                    },
                    "finish_reason": "stop"
                }
            ]
        }

    except Exception as e:
        return {"error": str(e)}
