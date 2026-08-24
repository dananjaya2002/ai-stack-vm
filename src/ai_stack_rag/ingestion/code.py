"""Symbol-aware code ingestion with stable Qdrant point identifiers."""

import os
import sys
import re
import hashlib
from pathlib import Path
from typing import Any, Dict, List

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
)
from ai_stack_rag.chunking import code as code_chunking
from ai_stack_rag.embeddings.provider import EmbeddingProvider
from ai_stack_rag.utils.legacy_config import (
    default_config_path,
    load_json_object,
    require_string_map,
    require_string_set,
    require_symbol_patterns,
)
from ai_stack_rag.utils.source_locations import canonical_source_path


# -----------------------------
# Environment configuration
# -----------------------------

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "code-memory")

# Phase 2 default: repos live in memory/code-memory, not ai-stack/repos.
REPOS_ROOT = Path(
    os.getenv(
        "REPOS_ROOT",
        str(Path.home() / "ai-stack" / "memory" / "code-memory")
    )
)

EMBED_MODEL_NAME = os.getenv("EMBED_MODEL_NAME", "all-MiniLM-L6-v2")
EMBEDDING_DEVICE = os.getenv("EMBEDDING_DEVICE", "cpu")

CHUNK_MAX_CHARS = int(os.getenv("CHUNK_MAX_CHARS", "2200"))
CHUNK_OVERLAP_CHARS = int(os.getenv("CHUNK_OVERLAP_CHARS", "300"))
CODE_INDEX_CONFIG_FILE = default_config_path("CODE_INDEX_CONFIG_FILE", "code_index.json", __file__)
CODE_INDEX_CONFIG = load_json_object(CODE_INDEX_CONFIG_FILE, "Code index")


# -----------------------------
# Ignore configuration
# -----------------------------

IGNORE_DIRS = require_string_set(CODE_INDEX_CONFIG, "ignore_dirs", "Code index")
IGNORE_SUFFIXES = require_string_set(CODE_INDEX_CONFIG, "ignore_suffixes", "Code index", lowercase=True)
LANG_BY_EXT = require_string_map(CODE_INDEX_CONFIG, "language_by_extension", "Code index")


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
    name = path.name.lower()

    if name == "dockerfile" or name.endswith(".dockerfile"):
        return "dockerfile"

    return LANG_BY_EXT.get(path.suffix.lower(), "text")


def detect_category(path: Path, language: str) -> str:
    name = path.name.lower()
    path_text = str(path).lower()

    if language == "markdown":
        return "docs"

    if language in {"yaml", "json", "toml", "ini", "env", "dockerfile"}:
        return "config"

    if name in {"docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"}:
        return "config"

    if "test" in path_text or "spec" in path_text:
        return "test"

    return "code"


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


def chunk_text_spans(text: str, base_offset: int = 0) -> List[Dict[str, object]]:
    if not text.strip():
        return []

    chunks: List[Dict[str, object]] = []
    content_start = len(text) - len(text.lstrip())
    content_end = len(text.rstrip())
    start = content_start

    while start < content_end:
        end = min(start + CHUNK_MAX_CHARS, content_end)

        # Try to end at a clean newline boundary when possible.
        if end < content_end:
            newline_pos = text.rfind("\n", start, end)
            if newline_pos > start + 500:
                end = newline_pos

        raw_chunk = text[start:end]
        left_trim = len(raw_chunk) - len(raw_chunk.lstrip())
        right_trim = len(raw_chunk.rstrip())
        chunk = raw_chunk[left_trim:right_trim]

        if chunk:
            chunks.append(
                {
                    "text": chunk,
                    "char_start": base_offset + start + left_trim,
                    "char_end": base_offset + start + right_trim,
                }
            )

        if end >= content_end:
            break

        start = max(content_start, end - CHUNK_OVERLAP_CHARS)

    return chunks


def chunk_text(text: str) -> List[str]:
    return [str(chunk["text"]) for chunk in chunk_text_spans(text)]


# -----------------------------
# Symbol extraction
# -----------------------------

SYMBOL_PATTERNS = require_symbol_patterns(CODE_INDEX_CONFIG, "symbol_patterns", "Code index")


def extract_symbols(text: str, language: str) -> List[Dict[str, object]]:
    symbols: List[Dict[str, object]] = []

    if language == "markdown":
        for match in re.finditer(r"^(#{1,6})\s+(.+)$", text, re.MULTILINE):
            symbols.append(
                {
                    "symbol_type": "markdown_section",
                    "symbol_name": match.group(2).strip(),
                    "start": match.start(),
                }
            )
        return sorted(symbols, key=lambda x: int(x["start"]))

    patterns = SYMBOL_PATTERNS.get(language, [])

    for symbol_type, pattern in patterns:
        for match in pattern.finditer(text):
            if symbol_type == "fastapi_route":
                symbol_name = f"app.{match.group(1)}"
            else:
                symbol_name = match.group(1) if match.groups() else symbol_type

            symbols.append(
                {
                    "symbol_type": symbol_type,
                    "symbol_name": symbol_name,
                    "start": match.start(),
                }
            )

    return sorted(symbols, key=lambda x: int(x["start"]))


def chunk_text_with_symbols(text: str, language: str) -> List[Dict[str, object]]:
    if not text:
        return []

    symbols = extract_symbols(text, language)

    # If no symbols were found, fall back to normal overlapping text chunks.
    if not symbols:
        chunks = chunk_text_spans(text)
        for chunk in chunks:
            chunk.update(
                {
                    "symbol_type": "text_chunk",
                    "symbol_name": None,
                    "symbol_subchunk_index": 0,
                }
            )
        return chunks

    chunks: List[Dict[str, object]] = []

    # Include preamble/imports before first symbol as one chunk when useful.
    first_symbol_start = int(symbols[0]["start"])
    if first_symbol_start > 0:
        preamble = text[:first_symbol_start].strip()
        if preamble:
            for sub_index, sub_chunk in enumerate(
                chunk_text_spans(text[:first_symbol_start])
            ):
                chunks.append(
                    {
                        **sub_chunk,
                        "symbol_type": "file_preamble",
                        "symbol_name": "file_preamble",
                        "symbol_subchunk_index": sub_index,
                    }
                )

    for i, symbol in enumerate(symbols):
        start = int(symbol["start"])
        end = int(symbols[i + 1]["start"]) if i + 1 < len(symbols) else len(text)

        symbol_text = text[start:end]
        if not symbol_text.strip():
            continue

        sub_chunks = chunk_text_spans(symbol_text, base_offset=start)

        for sub_index, sub_chunk in enumerate(sub_chunks):
            chunks.append(
                {
                    **sub_chunk,
                    "symbol_type": symbol["symbol_type"],
                    "symbol_name": symbol["symbol_name"],
                    "symbol_subchunk_index": sub_index,
                }
            )

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


def index_file(client: QdrantClient, model: Any, repo_root: Path, file_path: Path):
    file_path = file_path.resolve()
    repo_root = repo_root.resolve()

    if code_chunking.should_ignore(file_path, IGNORE_DIRS, IGNORE_SUFFIXES):
        return 0

    if not file_path.is_file():
        return 0

    try:
        relative_path = str(file_path.relative_to(repo_root))
    except Exception:
        relative_path = str(file_path)

    repo = repo_root.name
    language = code_chunking.detect_language(file_path, LANG_BY_EXT)
    category = code_chunking.detect_category(file_path, language)
    text = read_file(file_path)

    if not text.strip():
        return 0

    chunks = code_chunking.chunk_text_with_symbols(
        text,
        language,
        SYMBOL_PATTERNS,
        CHUNK_MAX_CHARS,
        CHUNK_OVERLAP_CHARS,
    )

    if not chunks:
        return 0

    delete_existing_file_chunks(client, repo, relative_path)

    prepared_chunks = []

    for chunk_index, chunk in enumerate(chunks):
        chunk_text_value = str(chunk.get("text") or "").strip()

        if not chunk_text_value:
            continue

        prepared_chunks.append((chunk_index, chunk, chunk_text_value))

    if not prepared_chunks:
        return 0

    embeddings = model.encode_many(
        [chunk_text_value for _, _, chunk_text_value in prepared_chunks]
    )
    if len(embeddings) != len(prepared_chunks):
        raise RuntimeError(
            "Embedding provider returned an unexpected number of vectors: "
            f"expected {len(prepared_chunks)}, received {len(embeddings)}"
        )
    points = []

    for (chunk_index, chunk, chunk_text_value), embedding in zip(
        prepared_chunks, embeddings
    ):
        char_start = int(chunk.get("char_start") or 0)
        char_end = int(chunk.get("char_end") or char_start)
        line_start = text.count("\n", 0, char_start) + 1
        line_end = text.count("\n", 0, char_end) + 1
        source_path = canonical_source_path(
            "code",
            repo_name=repo,
            relative_path=relative_path,
            file_path=file_path,
        )

        payload = {
            "repo": repo,
            "file": str(file_path),
            "relative_path": relative_path,
            "source_path": source_path,
            "line_start": line_start,
            "line_end": line_end,
            "language": language,
            "category": category,
            "symbol_type": chunk.get("symbol_type"),
            "symbol_name": chunk.get("symbol_name"),
            "symbol_subchunk_index": chunk.get("symbol_subchunk_index", 0),
            "chunk_index": chunk_index,
            "text": chunk_text_value,
        }

        points.append(
            PointStruct(
                id=code_chunking.stable_id(repo, relative_path, chunk_index),
                vector=embedding,
                payload=payload,
            )
        )

    if not points:
        return 0

    client.upsert(
        collection_name=QDRANT_COLLECTION,
        points=points,
        wait=True,
    )

    print(
        f"✅ Indexed: {repo}/{relative_path} | "
        f"language={language} | category={category} | chunks={len(points)}"
    )
    return len(points)


def collect_files(target: Path) -> List[Path]:
    target = target.resolve()

    if target.is_file():
        return [target]

    files = []

    for path in target.rglob("*"):
        if path.is_file() and not code_chunking.should_ignore(path, IGNORE_DIRS, IGNORE_SUFFIXES):
            files.append(path)

    return files


def index_targets(targets: List[Path]):
    print("========================================")
    print("Code indexer starting")
    print("========================================")
    print(f"Qdrant: {QDRANT_HOST}:{QDRANT_PORT}")
    print(f"Collection: {QDRANT_COLLECTION}")
    print(f"Embedding model: {EMBED_MODEL_NAME}")
    print(f"Repos root: {REPOS_ROOT}")
    print(f"Targets: {len(targets)}")
    print("========================================")

    model = EmbeddingProvider(EMBED_MODEL_NAME, EMBEDDING_DEVICE)
    vector_size = model.dimension()

    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    ensure_collection(client, vector_size)

    files_by_path = {}

    for target in targets:
        target = target.resolve()

        if not target.exists():
            print(f"❌ Target does not exist: {target}")
            sys.exit(1)

        for file_path in collect_files(target):
            resolved_path = file_path.resolve()
            files_by_path[str(resolved_path)] = resolved_path

    files = [files_by_path[path] for path in sorted(files_by_path)]

    print(f"Files selected for indexing: {len(files)}")

    total_chunks = 0
    indexed_files = 0

    for file_path in files:
        repo_root = find_repo_root(file_path)
        chunk_count = index_file(client, model, repo_root, file_path)

        if chunk_count > 0:
            indexed_files += 1
            total_chunks += chunk_count

    print("========================================")
    print("Indexing complete")
    print(f"Indexed files: {indexed_files}")
    print(f"Total chunks: {total_chunks}")
    print("========================================")


def index_target(target: Path):
    index_targets([target])


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage:")
        print(
            "  python -m ai_stack_rag.ingestion.code "
            "<repo-or-file-path> [more-paths ...]"
        )
        sys.exit(1)

    index_targets([Path(value) for value in sys.argv[1:]])


if __name__ == "__main__":
    main()
