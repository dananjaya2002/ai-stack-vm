import os
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer


QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "code-memory")
EMBED_MODEL_NAME = os.getenv("EMBED_MODEL_NAME", "all-MiniLM-L6-v2")


def main():
    model = SentenceTransformer(EMBED_MODEL_NAME)
    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

    while True:
        query = input("\nCode search query: ").strip()

        if not query:
            break

        vector = model.encode(query).tolist()

        results = client.search(
            collection_name=QDRANT_COLLECTION,
            query_vector=vector,
            limit=8,
        )

        for result in results:
            payload = result.payload or {}
            print("\n---")
            print("Score:", result.score)
            print("Repo:", payload.get("repo"))
            print("File:", payload.get("relative_path"))
            print("Language:", payload.get("language"))
            print("Chunk:", payload.get("chunk_index"))
            print((payload.get("text") or "")[:1000])


if __name__ == "__main__":
    main()
