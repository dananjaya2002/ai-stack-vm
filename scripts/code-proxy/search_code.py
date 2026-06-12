import os
from collections import OrderedDict

from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer


# -----------------------------
# Environment configuration
# -----------------------------

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "code-memory")

EMBED_MODEL_NAME = os.getenv("EMBED_MODEL_NAME", "all-MiniLM-L6-v2")

TOP_K = int(os.getenv("CODE_TOP_K", "5"))
SEARCH_LIMIT_MULTIPLIER = int(os.getenv("SEARCH_LIMIT_MULTIPLIER", "4"))

# For code search, 0.25 is better than 0.4 during early testing.
SCORE_THRESHOLD = float(os.getenv("CODE_SCORE_THRESHOLD", "0.25"))


def print_collection_info(client: QdrantClient) -> bool:
    try:
        info = client.get_collection(QDRANT_COLLECTION)
    except Exception as e:
        print(f"❌ Could not read collection: {QDRANT_COLLECTION}")
        print(f"Error: {e}")
        print()
        print("Fix:")
        print("  1. Make sure Qdrant is running.")
        print("  2. Run index_code.py first.")
        print("  3. Confirm QDRANT_COLLECTION is set to code-memory.")
        return False

    print(f"✅ Collection exists: {QDRANT_COLLECTION}")

    points_count = getattr(info, "points_count", None)
    indexed_vectors_count = getattr(info, "indexed_vectors_count", None)

    print(f"📦 Points count: {points_count}")

    if indexed_vectors_count is not None:
        print(f"📦 Indexed vectors count: {indexed_vectors_count}")

    if points_count == 0:
        print()
        print("⚠️ Collection exists but has 0 points.")
        print("Run index_code.py first.")
        return False

    return True


def query_qdrant(client: QdrantClient, query_vector, limit: int):
    """
    Supports modern qdrant-client query_points API.
    """
    return client.query_points(
        collection_name=QDRANT_COLLECTION,
        query=query_vector,
        limit=limit,
    )


def display_raw_matches(results, max_items: int = 10):
    print()
    print("Top raw matches:")

    if not results.points:
        print("  No raw results returned from Qdrant.")
        return

    for i, r in enumerate(results.points[:max_items], start=1):
        payload = r.payload or {}

        print(
            f"  {i}. score={round(r.score, 4)} | "
            f"repo={payload.get('repo')} | "
            f"file={payload.get('relative_path')} | "
            f"chunk={payload.get('chunk_index')} | "
            f"lang={payload.get('language')}"
        )


def group_filtered_results(results):
    file_chunks = OrderedDict()

    for r in results.points:
        score = r.score

        if score < SCORE_THRESHOLD:
            continue

        payload = r.payload or {}

        file = payload.get("relative_path", "unknown")
        text = payload.get("text", "")
        category = payload.get("category", "code")
        repo = payload.get("repo", "unknown")
        language = payload.get("language", "text")
        chunk_idx = payload.get("chunk_index", 0)

        if file not in file_chunks:
            file_chunks[file] = []

        file_chunks[file].append(
            {
                "score": score,
                "text": text,
                "category": category,
                "repo": repo,
                "language": language,
                "chunk_index": chunk_idx,
            }
        )

    return file_chunks


def display_filtered_results(file_chunks):
    result_count = 0

    print()
    print(f"Filtered results using threshold: {SCORE_THRESHOLD}")

    if not file_chunks:
        print("No chunks passed the score threshold.")
        print()
        print("Try:")
        print("  CODE_SCORE_THRESHOLD=0.0 python ~/ai-stack/code-proxy/search_code.py")
        print("  CODE_SCORE_THRESHOLD=0.20 python ~/ai-stack/code-proxy/search_code.py")
        print("  CODE_SCORE_THRESHOLD=0.25 python ~/ai-stack/code-proxy/search_code.py")
        return

    for file, chunks in file_chunks.items():
        chunks = sorted(chunks, key=lambda x: x["score"], reverse=True)

        print()
        print(f"📁 File: {file}")

        for item in chunks[:2]:
            result_count += 1

            print()
            print(f"--- Chunk {result_count} ---")
            print(f"Repository: {item['repo']} | Language: {item['language']}")
            print(f"Category: {item['category']} | Chunk Index: {item['chunk_index']}")
            print(f"Match Score: {round(item['score'], 4)}")
            print("-" * 60)
            print((item["text"] or "")[:1200])
            print("-" * 60)

            if result_count >= TOP_K:
                break

        if result_count >= TOP_K:
            break


def main():
    print("========================================")
    print("Code search tool")
    print("========================================")
    print(f"Qdrant: {QDRANT_HOST}:{QDRANT_PORT}")
    print(f"Collection: {QDRANT_COLLECTION}")
    print(f"Embedding model: {EMBED_MODEL_NAME}")
    print(f"TOP_K: {TOP_K}")
    print(f"SCORE_THRESHOLD: {SCORE_THRESHOLD}")
    print("========================================")

    model = SentenceTransformer(EMBED_MODEL_NAME)
    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

    if not print_collection_info(client):
        return

    while True:
        query = input("\nCode search query (or 'exit'): ").strip()

        if not query or query.lower() == "exit":
            print("Exiting.")
            break

        print()
        print(f"🔍 Searching for: {query}")

        query_vector = model.encode(query).tolist()

        limit = TOP_K * SEARCH_LIMIT_MULTIPLIER

        results = query_qdrant(
            client=client,
            query_vector=query_vector,
            limit=limit,
        )

        print(f"Raw results returned: {len(results.points)}")

        display_raw_matches(results)

        file_chunks = group_filtered_results(results)

        display_filtered_results(file_chunks)


if __name__ == "__main__":
    main()
