from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer


QDRANT_HOST = "localhost"
QDRANT_PORT = 6333
COLLECTION_NAME = "engineering-memory"


client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
model = SentenceTransformer("all-MiniLM-L6-v2")


def search(query, top_k=5):
    print(f"\nSearching for: {query}\n")

    query_vector = model.encode(query).tolist()

    results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        limit=top_k
    )

    if not results.points:
        print("❌ No results found")
        return

    for i, result in enumerate(results.points, 1):
        payload = result.payload or {}

        print(f"\n--- Result {i} ---")
        print(f"File: {payload.get('file', 'unknown')}")

        text = payload.get("text", "")
        print(text[:500] if text else "⚠️ No text found")


if __name__ == "__main__":
    while True:
        q = input("\nEnter query (or 'exit'): ")
        if q.lower() == "exit":
            break
        search(q)
