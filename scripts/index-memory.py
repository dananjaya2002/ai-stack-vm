import os
import uuid
from pathlib import Path
from tqdm import tqdm

from qdrant_client import QdrantClient
from qdrant_client.models import (
    VectorParams,
    Distance,
    Filter,
    FieldCondition,
    MatchValue,
)

from sentence_transformers import SentenceTransformer


# CONFIG
MEMORY_DIR = Path.home() / "ai-stack/memory"
QDRANT_HOST = "localhost"
QDRANT_PORT = 6333
COLLECTION_NAME = "engineering-memory"

CHUNK_SIZE = 500  # characters


# INIT MODEL
print("Loading embedding model...")
model = SentenceTransformer("all-MiniLM-L6-v2")


# INIT QDRANT
client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)


# CREATE COLLECTION IF NOT EXISTS
collections = client.get_collections().collections
collection_names = [c.name for c in collections]

if COLLECTION_NAME not in collection_names:
    print(f"Creating collection: {COLLECTION_NAME}")
    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(
            size=384,
            distance=Distance.COSINE
        ),
    )
else:
    print(f"Using existing collection: {COLLECTION_NAME}")


# HELPER FUNCTIONS
def chunk_text(text, chunk_size=CHUNK_SIZE):
    return [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]


def load_files():
    files = []
    for root, _, filenames in os.walk(MEMORY_DIR):
        for fname in filenames:
            path = Path(root) / fname
            if path.suffix.lower() in [".md", ".txt", ".py", ".json", ".yaml", ".yml"]:
                files.append(path)
    return files


# MAIN INDEX FUNCTION
def index(file_path=None):
    if file_path:
        files = [Path(file_path)]
        print(f"📄 Incremental indexing: {file_path}")
    else:
        files = load_files()
        print(f"📁 Full indexing: {len(files)} files")

    all_points = []

    for file_path in tqdm(files, desc="Indexing"):
        if not file_path.exists():
            print(f"⚠️ Skipping deleted file: {file_path}")
            continue

        try:
            text = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            print(f"⚠️ Failed to read: {file_path}")
            continue

        chunks = chunk_text(text)

        # ✅ FIXED DELETE (Qdrant new API)
        try:
            client.delete(
                collection_name=COLLECTION_NAME,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="file",
                            match=MatchValue(value=str(file_path))
                        )
                    ]
                )
            )
        except Exception as e:
            print(f"⚠️ Delete failed for {file_path}: {e}")

        # CREATE NEW POINTS
        for idx, chunk in enumerate(chunks):
            embedding = model.encode(chunk).tolist()

            point = {
                "id": str(uuid.uuid4()),
                "vector": embedding,
                "payload": {
                    "file": str(file_path),
                    "chunk_index": idx,
                    "text": chunk
                }
            }

            all_points.append(point)

    # NO DATA
    if not all_points:
        print("⚠️ No data to upload.")
        return

    print(f"Uploading {len(all_points)} chunks...")

    # ✅ SAFE BATCHING
    BATCH_SIZE = 100

    for i in range(0, len(all_points), BATCH_SIZE):
        batch = all_points[i:i + BATCH_SIZE]

        client.upsert(
            collection_name=COLLECTION_NAME,
            points=batch
        )

    print("✅ Done!")


# ENTRY POINT
if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        index(sys.argv[1])   # incremental
    else:
        index()              # full
