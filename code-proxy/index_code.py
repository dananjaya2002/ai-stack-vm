import os
import sys
import hashlib
from pathlib import Path
from typing import List, Dict

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
from sentence_transformers import SentenceTransformer


QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "code-memory")
REPOS_ROOT = Path(os.getenv("REPOS_ROOT", "/repos"))

EMBED_MODEL_NAME = os.getenv("EMBED_MODEL_NAME", "all-MiniLM-L6-v2")

CHUNK_MAX_CHARS = int(os.getenv("CHUNK_MAX_CHARS", "2200"))
CHUNK_OVERLAP_CHARS = int(os.getenv("CHUNK_OVERLAP_CHARS", "300"))

IGNORE_DIRS = {
    ".git",
    "node_modules",
    "dist",
    "build",
    "target",
    ".next",
    ".nuxt",
    "coverage",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    ".idea",
    ".vscode",
}

IGNORE_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico",
    ".zip", ".tar", ".gz", ".7z",
    ".pdf", ".docx", ".xlsx", ".pptx",
    ".lock", ".log", ".map",
    ".gguf", ".bin", ".onnx",
}

LANG_BY_EXT = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascriptreact",
    ".ts": "typescript",
    ".tsx": "typescriptreact",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".php": "php",
    ".rb": "ruby",
    ".sh": "shell",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".md": "markdown",
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
    ".sql": "sql",
}


def should_ignore(path: Path) -> bool:
    parts = set(path.parts)

    if parts.intersection(IGNORE_DIRS):
        return True

    if path.suffix.lower() in IGNORE_SUFFIXES:
        return True

    if path.name.startswith(".env"):
        return True

    return False


def detect_language(path: Path) -> str:
    return LANG_BY_EXT.get(path.suffix.lower(), "text")


def stable_id(repo: str, relative_path: str, chunk_index: int) -> int:
    raw = f"{repo}:{relative_path}:{chunk_index}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def chunk_text(text: str) -> Listchunks = []
    start = 0

    while start < len(text):
        end = start + CHUNK_MAX_CHARS
        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        start = end - CHUNK_OVERLAP_CHARS

        if start < 0:
            start = 0

        if start >= len(text):
            break

    return chunks


def read_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def ensure_collection(client: QdrantClient, vector_size: int):
    collections = client.get_collections().collections
    existing = {c.name for c in collections}

    if QDRANT_COLLECTION not in existing:
        client.create_collection(
            collection_name=QDRANT_COLLECTION,
            vectors_config=VectorParams(
                size=vector_size,
                distance=Distance.COSINE,
            ),
        )


def delete_existing_file_chunks(client: QdrantClient, repo: str, relative_path: str):
    client.delete(
        collection_name=QDRANT_COLLECTION,
        points_selector=Filter(
            must=[
                FieldCondition(
                    key="repo",
                    match=MatchValue(value=repo),
                ),
                FieldCondition(
                    key="relative_path",
                    match=MatchValue(value=relative_path),
                ),
            ]
        ),
    )


def index_file(client: QdrantClient, model: SentenceTransformer, repo_root: Path, file_path: Path):
    repo = repo_root.name
    relative_path = str(file_path.relative_to(repo_root))

    if should_ignore(file_path):
        return

    text = read_file(file_path)

    if not text.strip():
        return

    language = detect_language(file_path)
    chunks = chunk_text(text)

    delete_existing_file_chunks(client, repo, relative_path)

    points = []

    for i, chunk in enumerate(chunks):
        embedding = model.encode(chunk).tolist()

        payload = {
            "repo": repo,
            "file": str(file_path),
            "relative_path": relative_path,
            "language": language,
            "category": "code",
            "chunk_index": i,
            "text": chunk,
        }

        points.append(
            PointStruct(
                id=stable_id(repo, relative_path, i),
                vector=embedding,
                payload=payload,
            )
        )

    if points:
        client.upsert(
            collection_name=QDRANT_COLLECTION,
            points=points,
        )

    print(f"Indexed {relative_path}: {len(points)} chunks")


def index_repo_or_file(target: Path):
    model = SentenceTransformer(EMBED_MODEL_NAME)
    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

    vector_size = len(model.encode("test"))
    ensure_collection(client, vector_size)

    target = target.resolve()

    if target.is_file():
        repo_root = find_repo_root(target)
        index_file(client, model, repo_root, target)
        return

    repo_root = target

    for path in repo_root.rglob("*"):
        if path.is_file() and not should_ignore(path):
            index_file(client, model, repo_root, path)


def find_repo_root(file_path: Path) -> Path:
    current = file_path.parent

    while current != current.parent:
        if (current / ".git").exists():
            return current
        if current.parent == REPOS_ROOT:
            return current
        current = current.parent

    return file_path.parent


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python index_code.py /repos/<repo-name> or /repos/<repo-name>/file.py")
        sys.exit(1)

    index_repo_or_file(Path(sys.argv[1]))
