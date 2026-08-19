"""Command-line memory retrieval implementation."""

import sys
from qdrant_client import QdrantClient
from ai_stack_rag.embeddings.provider import EmbeddingProvider

QDRANT_HOST = "localhost"
QDRANT_PORT = 6333
COLLECTION_NAME = "engineering-memory"

TOP_K = 5
SCORE_THRESHOLD = 0.6

client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
model = EmbeddingProvider("all-MiniLM-L6-v2")


def search(query):
    print(f"\n🔍 Searching for: {query}\n")

    query_vector = model.encode(query)

    results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        limit=TOP_K * 4
    )

    file_chunks = {}

    for r in results.points:
        payload = r.payload or {}

        file = payload.get("file", "unknown")
        text = payload.get("text", "")
        category = payload.get("category", "unknown")
        score = r.score

        if score < SCORE_THRESHOLD:
            continue

        if file not in file_chunks:
            file_chunks[file] = []

        file_chunks[file].append((score, text, category))

    result_count = 0

    for file, chunks in file_chunks.items():
        chunks = sorted(chunks, key=lambda x: x[0], reverse=True)

        print(f"\n📁 File: {file}")

        for score, text, category in chunks[:2]:
            result_count += 1

            print(f"\n--- Chunk {result_count} ---")
            print(f"Category: {category}")
            print(f"Score: {round(score, 3)}")
            print("-" * 40)
            print(text[:400])

            if result_count >= TOP_K:
                return


def main():
    if len(sys.argv) > 1:
        search(" ".join(sys.argv[1:]))
        return
    while True:
        q = input("\nEnter query (or 'exit'): ")
        if q.lower() == "exit":
            break
        search(q)


if __name__ == "__main__":
    main()
