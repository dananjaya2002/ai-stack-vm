from fastapi import FastAPI
from pydantic import BaseModel

from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

import requests

import os
import json
import time
from pathlib import Path

LOG_FILE = Path(os.getenv("MEMORY_API_LOG_FILE", "/tmp/memory_api.log"))
ENABLE_LOGGING = os.getenv("MEMORY_API_LOGS", "false").lower() == "true"


# CONFIG
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "engineering-memory")

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:8082/v1")
LLAMA_API = f"{LLM_BASE_URL.rstrip('/')}/chat/completions"
MODEL_NAME = os.getenv("LLM_MODEL", "qwen2.5-coder-7b-instruct-q4_k_m.gguf")

TOP_K = int(os.getenv("MEMORY_TOP_K", "5"))
SCORE_THRESHOLD = float(os.getenv("MEMORY_SCORE_THRESHOLD", "0.5"))


app = FastAPI()

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
def query_model(prompt):
    try:
        res = requests.post(
            LLAMA_API,
            json={
                "model": MODEL_NAME,
                "messages": [
                    {"role": "user", "content": prompt}
                ]
            },
            timeout=60
        )

        data = res.json()
        return data["choices"][0]["message"]["content"]

    except Exception as e:
        return f"⚠️ Model error: {e}"

# -----------------------------
# log event
# -----------------------------

def log_event(data):
    if not ENABLE_LOGGING:
        return

    entry = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        **data
    }

    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")



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

        contexts = search_memory(user_msg)
        prompt = build_prompt(user_msg, contexts)

        # ✅ Added pre-inference log
        log_event({
            "type": "prompt_built",
            "query": user_msg,
            "context_size": len(contexts)
        })

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