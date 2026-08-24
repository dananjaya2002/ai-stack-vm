"""Engineering-memory ingestion with backward-compatible Qdrant payloads."""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

from qdrant_client.models import FieldCondition, Filter, MatchValue, PayloadSchemaType
from tqdm import tqdm

from ai_stack_rag.chunking.text import chunk_text
from ai_stack_rag.embeddings.provider import EmbeddingProvider
from ai_stack_rag.ingestion.loaders import iter_memory_files, load_document
from ai_stack_rag.utils.config import load_settings
from ai_stack_rag.vectordb.qdrant import QdrantStore


def _runtime() -> tuple[Path, str, EmbeddingProvider, QdrantStore]:
    settings = load_settings()
    memory_root = Path(
        os.getenv("MEMORY_DIR", os.getenv("MEMORY_ROOT", settings.ingestion.memory_root))
    )
    collection = os.getenv(
        "QDRANT_COLLECTION",
        os.getenv("MEMORY_QDRANT_COLLECTION", settings.vector_db.memory_collection),
    )
    embedder = EmbeddingProvider(settings.embeddings.model, settings.embeddings.device)
    store = QdrantStore(
        settings.vector_db.host,
        settings.vector_db.port,
        collection,
    )
    return memory_root, collection, embedder, store


def load_files(root: Path | None = None) -> list[Path]:
    if root is None:
        root, _, _, _ = _runtime()
    return iter_memory_files(root)


def index(file_path: str | Path | None = None) -> None:
    memory_root, collection, embedder, store = _runtime()
    settings = load_settings()
    print("Loading embedding model...")
    store.ensure_collection(embedder.dimension())
    try:
        store.client.create_payload_index(
            collection_name=collection,
            field_name="file_name",
            field_schema=PayloadSchemaType.KEYWORD,
        )
    except Exception as exc:
        print(f"Warning: could not ensure file_name payload index: {exc}")

    files = [Path(file_path)] if file_path else iter_memory_files(memory_root)
    print(
        f"Incremental indexing: {file_path}"
        if file_path
        else f"Full indexing: {len(files)} files"
    )
    points: list[dict[str, object]] = []
    for path in tqdm(files, desc="Indexing"):
        document = load_document(path)
        if document is None:
            print(f"Skipping unreadable or deleted file: {path}")
            continue
        try:
            store.delete(
                Filter(
                    must=[FieldCondition(key="file", match=MatchValue(value=str(path)))]
                ),
                wait=True,
            )
        except Exception as exc:
            print(f"Delete failed for {path}: {exc}")
        for chunk_index, text in enumerate(
            chunk_text(document.text, settings.chunking.memory_size)
        ):
            points.append(
                {
                    "id": str(uuid.uuid4()),
                    "vector": embedder.encode(text),
                    "payload": {
                        "file": str(path),
                        "file_name": path.name.lower(),
                        "chunk_index": chunk_index,
                        "category": path.parent.name,
                        "text": text,
                    },
                }
            )
    if not points:
        print("No data to upload.")
        return
    print(f"Uploading {len(points)} chunks...")
    for offset in range(0, len(points), 100):
        store.upsert(points[offset:offset + 100], wait=True)
    print("Done!")


def main() -> None:
    index(sys.argv[1] if len(sys.argv) > 1 else None)


if __name__ == "__main__":
    main()
