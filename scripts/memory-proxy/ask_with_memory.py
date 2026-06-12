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


# INIT
client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
embed_model = SentenceTransformer("all-MiniLM-L6-v2")


def search_memory(query):
    query_vector = embed_model.encode(query).tolist()

    results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        limit=TOP_K
    )

    contexts = []
    for r in results.points:
        payload = r.payload or {}
        text = payload.get("text", "")
        contexts.append(text)

    return contexts


def build_prompt(query, contexts):
    context_text = "\n\n".join(contexts)

    prompt = f"""
You are an expert software engineering assistant.

Use the following memory context to answer the question.

MEMORY:
{context_text}

QUESTION:
{query}

Answer clearly and practically. If memory is insufficient, still answer using reasoning.
"""
    return prompt.strip()


def query_model(prompt):
    response = requests.post(
        LLAMA_API,
        json={
            "model": MODEL_NAME,
            "messages": [
                {"role": "user", "content": prompt}
            ]
        }
    )

    data = response.json()

    return data["choices"][0]["message"]["content"]


def main():
    while True:
        query = input("\nAsk (or 'exit'): ")

        if query.lower() == "exit":
            break

        print("\n🔍 Searching memory...")
        contexts = search_memory(query)

        print(f"Found {len(contexts)} relevant chunks")

        print("\n🧠 Building prompt...")
        prompt = build_prompt(query, contexts)

        print("\n🤖 Querying model...\n")
        answer = query_model(prompt)

        print("✅ Answer:\n")
        print(answer)


if __name__ == "__main__":
    main()
