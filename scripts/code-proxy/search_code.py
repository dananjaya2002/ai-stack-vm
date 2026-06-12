import os
import json
import time
from pathlib import Path
from collections import OrderedDict
from typing import Any, Dict, List, Optional

from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer


# -----------------------------
# Environment configuration
# -----------------------------

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "code-memory")

EMBED_MODEL_NAME = os.getenv("EMBED_MODEL_NAME", "all-MiniLM-L6-v2")

# Final number of chunks/files shown to user
TOP_K = int(os.getenv("CODE_TOP_K", "8"))

# Fetch extra results from Qdrant, then filter/rerank locally
SEARCH_LIMIT_MULTIPLIER = int(os.getenv("SEARCH_LIMIT_MULTIPLIER", "4"))

# For code search, lower thresholds are often better during early testing
SCORE_THRESHOLD = float(os.getenv("CODE_SCORE_THRESHOLD", "0.25"))

# Per-file chunk limit prevents one file from flooding all context
MAX_CHUNKS_PER_FILE = int(os.getenv("MAX_CHUNKS_PER_FILE", "2"))

# Limit printed chunk size for terminal/debug output
MAX_TEXT_PREVIEW_CHARS = int(os.getenv("MAX_TEXT_PREVIEW_CHARS", "1200"))

# Logging
ENABLE_LOGGING = os.getenv("CODE_PROXY_LOGS", "false").lower() == "true"
LOG_FILE = Path(os.getenv("CODE_PROXY_LOG_FILE", "/tmp/code_proxy.log"))


# -----------------------------
# Logging
# -----------------------------

def log_event(event_type: str, data: Dict[str, Any]) -> None:
    if not ENABLE_LOGGING:
        return

    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

        entry = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "type": event_type,
            **data,
        }

        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    except Exception as e:
        # Do not break search because logging failed
        print(f"⚠️ Logging failed: {e}")


# -----------------------------
# Qdrant helpers
# -----------------------------

def create_client() -> QdrantClient:
    return QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)


def load_embedder() -> SentenceTransformer:
    return SentenceTransformer(EMBED_MODEL_NAME)


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


def query_qdrant(
    client: QdrantClient,
    query_vector: List[float],
    limit: int,
):
    """
    Modern qdrant-client search API.

    We explicitly request payload because code search needs:
    - repo
    - relative_path
    - language
    - category
    - chunk_index
    - text
    """
    return client.query_points(
        collection_name=QDRANT_COLLECTION,
        query=query_vector,
        limit=limit,
        with_payload=True,
        with_vectors=False,
    )


# -----------------------------
# Filtering / ranking
# -----------------------------

def should_keep_result(
    score: float,
    payload: Dict[str, Any],
    query: str,
    repo_filter: Optional[str] = None,
    language_filter: Optional[str] = None,
) -> bool:
    if score < SCORE_THRESHOLD:
        return False

    if repo_filter and payload.get("repo") != repo_filter:
        return False

    if language_filter and payload.get("language") != language_filter:
        return False

    # Optional lightweight intent filters
    query_lower = query.lower()
    relative_path = payload.get("relative_path", "").lower()
    language = payload.get("language", "").lower()
    text = payload.get("text", "").lower()

    # If query mentions frontend, prefer frontend-ish files but do not hard fail
    # because sometimes backend files are still relevant.
    if "frontend" in query_lower:
        if "frontend" not in relative_path and language not in {"tsx", "jsx", "typescript", "javascript"}:
            return score >= max(SCORE_THRESHOLD, 0.45)

    if "backend" in query_lower:
        if "backend" not in relative_path and language not in {"python", "typescript", "javascript", "go"}:
            return score >= max(SCORE_THRESHOLD, 0.45)

    if "docker" in query_lower:
        if "docker" not in relative_path and "docker" not in text:
            return score >= max(SCORE_THRESHOLD, 0.45)

    return True


def group_filtered_results(
    results,
    query: str,
    repo_filter: Optional[str] = None,
    language_filter: Optional[str] = None,
) -> OrderedDict:
    """
    Group chunks by file.

    This improves model efficiency because instead of sending many unrelated chunks,
    we send the best few chunks from the most relevant files.
    """
    file_chunks = OrderedDict()

    for r in results.points:
        payload = r.payload or {}
        score = float(r.score)

        log_event(
            "chunk_seen",
            {
                "score": score,
                "repo": payload.get("repo"),
                "relative_path": payload.get("relative_path"),
                "language": payload.get("language"),
                "chunk_index": payload.get("chunk_index"),
            },
        )

        if not should_keep_result(
            score=score,
            payload=payload,
            query=query,
            repo_filter=repo_filter,
            language_filter=language_filter,
        ):
            continue

        relative_path = payload.get("relative_path") or payload.get("file") or "unknown"

        item = {
            "score": score,
            "repo": payload.get("repo", "unknown"),
            "relative_path": relative_path,
            "file": payload.get("file"),
            "language": payload.get("language", "text"),
            "category": payload.get("category", "code"),
            "chunk_index": payload.get("chunk_index", 0),
            "text": payload.get("text", ""),
        }

        if relative_path not in file_chunks:
            file_chunks[relative_path] = []

        file_chunks[relative_path].append(item)

        log_event(
            "chunk_selected",
            {
                "score": score,
                "repo": item["repo"],
                "relative_path": item["relative_path"],
                "language": item["language"],
                "chunk_index": item["chunk_index"],
                "preview": item["text"][:160],
            },
        )

    return file_chunks


def select_best_chunks(file_chunks: OrderedDict) -> List[Dict[str, Any]]:
    """
    Select top chunks while preventing one file from dominating the final context.
    """
    selected = []

    for relative_path, chunks in file_chunks.items():
        chunks = sorted(chunks, key=lambda x: x["score"], reverse=True)

        for item in chunks[:MAX_CHUNKS_PER_FILE]:
            selected.append(item)

            if len(selected) >= TOP_K:
                return selected

    return selected[:TOP_K]


# -----------------------------
# Display
# -----------------------------

def display_raw_matches(results, max_items: int = 10) -> None:
    print()
    print("Top raw matches:")

    if not results.points:
        print("  No raw results returned from Qdrant.")
        return

    for i, r in enumerate(results.points[:max_items], start=1):
        payload = r.payload or {}

        print(
            f"  {i}. score={round(float(r.score), 4)} | "
            f"repo={payload.get('repo')} | "
            f"file={payload.get('relative_path')} | "
            f"chunk={payload.get('chunk_index')} | "
            f"lang={payload.get('language')}"
        )


def display_selected_chunks(chunks: List[Dict[str, Any]]) -> None:
    print()
    print(f"Filtered results using threshold: {SCORE_THRESHOLD}")
    print(f"Final selected chunks: {len(chunks)}")

    if not chunks:
        print("No chunks passed the score threshold.")
        print()
        print("Try:")
        print("  CODE_SCORE_THRESHOLD=0.0 python ~/ai-stack/scripts/code-proxy/search_code.py")
        print("  CODE_SCORE_THRESHOLD=0.20 python ~/ai-stack/scripts/code-proxy/search_code.py")
        print("  CODE_SCORE_THRESHOLD=0.25 python ~/ai-stack/scripts/code-proxy/search_code.py")
        return

    current_file = None

    for i, item in enumerate(chunks, start=1):
        if item["relative_path"] != current_file:
            current_file = item["relative_path"]
            print()
            print(f"📁 File: {current_file}")

        print()
        print(f"--- Chunk {i} ---")
        print(f"Repository: {item['repo']} | Language: {item['language']}")
        print(f"Category: {item['category']} | Chunk Index: {item['chunk_index']}")
        print(f"Match Score: {round(item['score'], 4)}")
        print("-" * 60)
        print((item["text"] or "")[:MAX_TEXT_PREVIEW_CHARS])
        print("-" * 60)


# -----------------------------
# Search flow
# -----------------------------

def search_code(
    query: str,
    model: SentenceTransformer,
    client: QdrantClient,
    repo_filter: Optional[str] = None,
    language_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    log_event(
        "search_query",
        {
            "query": query,
            "repo_filter": repo_filter,
            "language_filter": language_filter,
        },
    )

    query_vector = model.encode(query).tolist()

    limit = max(TOP_K * SEARCH_LIMIT_MULTIPLIER, TOP_K)

    results = query_qdrant(
        client=client,
        query_vector=query_vector,
        limit=limit,
    )

    print(f"Raw results returned: {len(results.points)}")

    display_raw_matches(results)

    file_chunks = group_filtered_results(
        results=results,
        query=query,
        repo_filter=repo_filter,
        language_filter=language_filter,
    )

    selected = select_best_chunks(file_chunks)

    log_event(
        "final_context",
        {
            "query": query,
            "raw_count": len(results.points),
            "file_count": len(file_chunks),
            "selected_count": len(selected),
            "selected": [
                {
                    "score": x["score"],
                    "repo": x["repo"],
                    "relative_path": x["relative_path"],
                    "language": x["language"],
                    "chunk_index": x["chunk_index"],
                }
                for x in selected
            ],
        },
    )

    return selected


# -----------------------------
# CLI
# -----------------------------

def main() -> None:
    print("========================================")
    print("Code search tool")
    print("========================================")
    print(f"Qdrant: {QDRANT_HOST}:{QDRANT_PORT}")
    print(f"Collection: {QDRANT_COLLECTION}")
    print(f"Embedding model: {EMBED_MODEL_NAME}")
    print(f"TOP_K: {TOP_K}")
    print(f"SEARCH_LIMIT_MULTIPLIER: {SEARCH_LIMIT_MULTIPLIER}")
    print(f"SCORE_THRESHOLD: {SCORE_THRESHOLD}")
    print(f"MAX_CHUNKS_PER_FILE: {MAX_CHUNKS_PER_FILE}")
    print(f"Logging: {ENABLE_LOGGING}")
    print(f"Log file: {LOG_FILE}")
    print("========================================")

    model = load_embedder()
    client = create_client()

    if not print_collection_info(client):
        return

    while True:
        query = input("\nCode search query or 'exit': ").strip()

        if not query or query.lower() == "exit":
            print("Exiting.")
            break

        repo_filter = input("Repo filter optional, press Enter to skip: ").strip() or None
        language_filter = input("Language filter optional, press Enter to skip: ").strip() or None

        print()
        print(f"🔍 Searching for: {query}")

        selected = search_code(
            query=query,
            model=model,
            client=client,
            repo_filter=repo_filter,
            language_filter=language_filter,
        )

        display_selected_chunks(selected)


if __name__ == "__main__":
    main()