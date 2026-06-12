import os
import sys
import hashlib
from pathlib import Path
from typing import List

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
)
from sentence_transformers import SentenceTransformer


# -----------------------------
# Environment configuration
# -----------------------------

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "code-memory")

REPOS_ROOT = Path(os.getenv("REPOS_ROOT", str(Path.home() / "ai-stack" / "repos")))

EMBED_MODEL_NAME = os.getenv("EMBED_MODEL_NAME", "all-MiniLM-L6-v2")

CHUNK_MAX_CHARS = int(os.getenv("CHUNK_MAX_CHARS", "2200"))
CHUNK_OVERLAP_CHARS = int(os.getenv("CHUNK_OVERLAP_CHARS", "300"))


# -----------------------------
# Ignore configuration
# -----------------------------

IGNORE_DIRS = {
    ".git",
    "node_modules",
    "dist",
    ".vite",
    "build",
    "target",
    ".next",
    ".nuxt",
    "coverage",
    "__pycache__",
    ".venv",
    "tmp",
    "temp",
    "cache",
    ".cache",
    "venv",
    "env",
    ".idea",
    ".vscode",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".terraform",
}

IGNORE_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".svg",
    ".zip",
    ".tar",
    ".gz",
    ".7z",
    ".rar",
    ".pdf",
    ".docx",
    ".xlsx",
    ".pptx",
    ".lock",
    ".log",
    ".map",
    ".gguf",
    ".bin",
    ".onnx",
    ".sqlite",
    ".db",
    ".mp4",
    ".mp3",
    ".wav",
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
    ".bash": "shell",
    ".zsh": "shell",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".md": "markdown",
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
    ".sql": "sql",
    ".xml": "xml",
    ".toml": "toml",
    ".ini": "ini",
    ".env": "env",
}


# -----------------------------
# Helpers
# -----------------------------

def should_ignore(path: Path) -> bool:
    path_parts = set(path.parts)

    if path_parts.intersection(IGNORE_DIRS):
        return True

    if path.suffix.lower() in IGNORE_SUFFIXES:
        return True

    if path.name.startswith(".env"):
        return True

    if path.name in {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock"}:
        return True

    return False


def detect_language(path: Path) -> str:
    return LANG_BY_EXT.get(path.suffix.lower(), "text")


def stable_id(repo: str, relative_path: str, chunk_index: int) -> int:
    raw = f"{repo}:{relative_path}:{chunk_index}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()

    # Qdrant integer point IDs must fit unsigned 64-bit range.
    return int(digest[:16], 16)


def read_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        print(f"⚠️ Could not read file: {path} | {e}")
        return ""


def chunk_text(text: str) -> List[str]:
    text = text.strip()

    if not text:
        return []

    chunks = []
    start = 0
    text_length = len(text)

    while start < text_length:
        end = min(start + CHUNK_MAX_CHARS, text_length)

        # Try to end at a clean newline boundary when possible.
        if end < text_length:
            newline_pos = text.rfind("\n", start, end)
            if newline_pos > start + 500:
                end = newline_pos

        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        if end >= text_length:
            break

        start = max(0, end - CHUNK_OVERLAP_CHARS)

    return chunks


def find_repo_root(path: Path) -> Path:
    path = path.resolve()

    if path.is_file():
        current = path.parent
    else:
        current = path

    # Prefer git root.
    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent

    # Fallback: if under REPOS_ROOT, repo root is first directory below REPOS_ROOT.
    try:
        relative = path.relative_to(REPOS_ROOT.resolve())
        if len(relative.parts) >= 1:
            return REPOS_ROOT.resolve() / relative.parts[0]
    except Exception:
        pass

    # Final fallback.
    return path.parent if path.is_file() else path


def ensure_collection(client: QdrantClient, vector_size: int):
    existing = {c.name for c in client.get_collections().collections}

    if QDRANT_COLLECTION not in existing:
        print(f"Creating Qdrant collection: {QDRANT_COLLECTION}")

        client.create_collection(
            collection_name=QDRANT_COLLECTION,
            vectors_config=VectorParams(
                size=vector_size,
                distance=Distance.COSINE,
            ),
        )
    else:
        print(f"Using existing Qdrant collection: {QDRANT_COLLECTION}")


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
        wait=True,
    )


def index_file(client: QdrantClient, model: SentenceTransformer, repo_root: Path, file_path: Path):
    file_path = file_path.resolve()
    repo_root = repo_root.resolve()

    if should_ignore(file_path):
        return 0

    if not file_path.is_file():
        return 0

    try:
        relative_path = str(file_path.relative_to(repo_root))
    except Exception:
        relative_path = str(file_path)

    repo = repo_root.name
    language = detect_language(file_path)
    text = read_file(file_path)

    if not text.strip():
        return 0

    chunks = chunk_text(text)

    if not chunks:
        return 0

    delete_existing_file_chunks(client, repo, relative_path)

    points = []

    for chunk_index, chunk in enumerate(chunks):
        embedding = model.encode(chunk).tolist()

        payload = {
            "repo": repo,
            "file": str(file_path),
            "relative_path": relative_path,
            "language": language,
            "category": "code",
            "chunk_index": chunk_index,
            "text": chunk,
        }

        points.append(
            PointStruct(
                id=stable_id(repo, relative_path, chunk_index),
                vector=embedding,
                payload=payload,
            )
        )

    client.upsert(
        collection_name=QDRANT_COLLECTION,
        points=points,
        wait=True,
    )

    print(f"✅ Indexed: {repo}/{relative_path} | language={language} | chunks={len(points)}")
    return len(points)


def collect_files(target: Path) -> List[Path]:
    target = target.resolve()

    if target.is_file():
        return [target]

    files = []

    for path in target.rglob("*"):
        if path.is_file() and not should_ignore(path):
            files.append(path)

    return files


def index_target(target: Path):
    print("========================================")
    print("Code indexer starting")
    print("========================================")
    print(f"Qdrant: {QDRANT_HOST}:{QDRANT_PORT}")
    print(f"Collection: {QDRANT_COLLECTION}")
    print(f"Embedding model: {EMBED_MODEL_NAME}")
    print(f"Repos root: {REPOS_ROOT}")
    print(f"Target: {target}")
    print("========================================")

    model = SentenceTransformer(EMBED_MODEL_NAME)
    vector_size = len(model.encode("vector-size-test"))

    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    ensure_collection(client, vector_size)

    target = target.resolve()

    if not target.exists():
        print(f"❌ Target does not exist: {target}")
        sys.exit(1)

    repo_root = find_repo_root(target)
    files = collect_files(target)

    print(f"Repo root detected: {repo_root}")
    print(f"Files selected for indexing: {len(files)}")

    total_chunks = 0
    indexed_files = 0

    for file_path in files:
        chunk_count = index_file(client, model, repo_root, file_path)

        if chunk_count > 0:
            indexed_files += 1
            total_chunks += chunk_count

    print("========================================")
    print("Indexing complete")
    print(f"Indexed files: {indexed_files}")
    print(f"Total chunks: {total_chunks}")
    print("========================================")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python index_code.py ~/ai-stack/repos/<repo-name>")
        print("  python index_code.py ~/ai-stack/repos/<repo-name>/path/to/file.py")
        sys.exit(1)

    index_target(Path(sys.argv[1]))
