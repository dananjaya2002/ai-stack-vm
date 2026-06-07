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
# MEMORY SEARCH
# -----------------------------
def search_memory(query):
    try:
        vector = embed_model.encode(query).tolist()

        results = client.query_points(
            collection_name=COLLECTION_NAME,
            query=vector,
            limit=TOP_K
        )

        contexts = [
            (r.payload or {}).get("text", "")
            for r in results.points
            if (r.payload or {}).get("text")
        ]

        return contexts

    except Exception as e:
        print(f"⚠️ Memory search failed: {e}")
        return []


# -----------------------------
# PROMPT BUILDER
# -----------------------------
def build_prompt(query, contexts):
    if contexts:
        context_text = "\n\n".join(contexts)

        return f"""
[MEMORY CONTEXT]

Use this memory to help answer:

{context_text}

[QUESTION]
{query}

Answer clearly and practically.
"""
    else:
        return f"""
No memory context found.

Question:
{query}
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
# ✅ OPENAI COMPATIBLE ENDPOINT
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

        # ✅ Extract latest user message
        user_msg = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_msg = msg.get("content", "")
                break

        if not user_msg:
            return {"error": "No user message found"}

        # 🔍 Memory search
        contexts = search_memory(user_msg)

        # 🧠 Build prompt
        context_text = "\n\n".join(contexts)

        enhanced_prompt = f"""
[MEMORY CONTEXT]

{context_text}

[USER QUESTION]
{user_msg}

Answer using memory if relevant, otherwise use reasoning.
"""

        # 🤖 Call model
        answer = query_model(enhanced_prompt)

        # ✅ OpenAI-compatible response
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
        return {
            "error": str(e)
        }
