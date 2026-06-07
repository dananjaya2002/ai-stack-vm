from fastapi import FastAPI
from pydantic import BaseModel

from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

import requests

# CONFIG
QDRANT_HOST = "localhost"
QDRANT_PORT = 6333
COLLECTION_NAME = "engineering-memory"

LLAMA_API = "http://localhost:8082/v1/chat/completions"
MODEL_NAME = "qwen2.5-coder-7b-instruct-q4_k_m.gguf"

TOP_K = 5
SCORE_THRESHOLD = 0.6  # ✅ relevance filter

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
        vector = embed_model.encode(query).tolist()

        results = client.query_points(
            collection_name=COLLECTION_NAME,
            query=vector,
            limit=TOP_K * 3  # ✅ fetch extra for filtering
        )

        contexts = []
        used_files = set()

        for r in results.points:
            payload = r.payload or {}
            text = payload.get("text", "")
            file = payload.get("file", "")
            category = payload.get("category", "unknown")

            # ✅ relevance filter
            if r.score < SCORE_THRESHOLD:
                continue

            # ✅ deduplicate (1 chunk per file)
            if file in used_files:
                continue

            # ✅ optional category-based filtering
            if "debug" in query.lower() and category != "debugging":
                continue
            if "persona" in query.lower() and category != "persons":
                continue

            if text:
                contexts.append(text)
                used_files.add(file)

            if len(contexts) >= TOP_K:
                break

        return contexts

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

        answer = query_model(prompt)

        return {
            "id": "memory-api",
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