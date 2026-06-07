from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

QDRANT_HOST = "localhost"
QDRANT_PORT = 6333
COLLECTION_NAME = "engineering-memory"

TOP_K = 5
SCORE_THRESHOLD = 0.6

client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
model = SentenceTransformer("all-MiniLM-L6-v2")


def search(query):
    print(f"\n🔍 Searching for: {query}\n")

    query_vector = model.encode(query).tolist()

    results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        limit=TOP_K * 3  # fetch extra for filtering
    )

    if not results.points:
        print("❌ No results found")
        return

    contexts = []
    used_files = set()

    for i, result in enumerate(results.points, 1):
        payload = result.payload or {}

        file = payload.get("file", "unknown")
        text = payload.get("text", "")
        category = payload.get("category", "unknown")
        score = result.score

        # ✅ relevance filter
        if score < SCORE_THRESHOLD:
            continue

        # ✅ deduplicate per file
        if file in used_files:
            continue

        used_files.add(file)
        contexts.append(text)

        print(f"\n--- Result {len(contexts)} ---")
        print(f"File: {file}")
        print(f"Category: {category}")
        print(f"Score: {round(score, 3)}")
        print("-" * 40)
        print(text[:500])

        if len(contexts) >= TOP_K:
            break

    if not contexts:
        print("⚠️ No relevant results after filtering")


if __name__ == "__main__":
    while True:
        q = input("\nEnter query (or 'exit'): ")
        if q.lower() == "exit":
            break
        search(q)