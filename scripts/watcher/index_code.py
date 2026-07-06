import os
import sys
import re
import json
import hashlib
import time
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
from sentence_transformers import SentenceTransformer


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

CHUNK_MAX_CHARS = int(os.getenv("CHUNK_MAX_CHARS", "2200"))
CHUNK_OVERLAP_CHARS = int(os.getenv("CHUNK_OVERLAP_CHARS", "300"))
CODE_INDEX_CONFIG_FILE = Path(
    os.getenv(
        "CODE_INDEX_CONFIG_FILE",
        str(Path(__file__).resolve().with_name("code_index_config.json")),
    )
)


def load_json_config(path: Path) -> Dict[str, Any]:
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Unable to load code index config: {path}") from exc
    if not isinstance(config, dict):
        raise RuntimeError(f"Code index config must be a JSON object: {path}")
    return config


def config_string_set(config: Dict[str, Any], key: str, *, lowercase: bool = False) -> set[str]:
    value = config.get(key)
    if not isinstance(value, list):
        raise RuntimeError(f"Code index config key must be a list: {key}")
    items = {
        str(item).strip().lower() if lowercase else str(item).strip()
        for item in value
        if str(item).strip()
    }
    if not items:
        raise RuntimeError(f"Code index config key must not be empty: {key}")
    return items


def config_string_map(config: Dict[str, Any], key: str) -> Dict[str, str]:
    value = config.get(key)
    if not isinstance(value, dict) or not value:
        raise RuntimeError(f"Code index config key must be a non-empty object: {key}")
    items = {
        str(map_key).strip().lower(): str(map_value).strip()
        for map_key, map_value in value.items()
        if str(map_key).strip() and str(map_value).strip()
    }
    if not items:
        raise RuntimeError(f"Code index config key must not be empty: {key}")
    return items


def compile_regex_flags(flag_names: List[str]) -> int:
    flags = 0
    for flag_name in flag_names:
        try:
            flags |= getattr(re, flag_name)
        except AttributeError as exc:
            raise RuntimeError(f"Unsupported regex flag in code index config: {flag_name}") from exc
    return flags


def config_symbol_patterns(config: Dict[str, Any]) -> Dict[str, List[tuple[str, re.Pattern[str]]]]:
    raw_patterns = config.get("symbol_patterns")
    if not isinstance(raw_patterns, dict) or not raw_patterns:
        raise RuntimeError("Code index config key must be a non-empty object: symbol_patterns")

    compiled_patterns: Dict[str, List[tuple[str, re.Pattern[str]]]] = {}
    for language, patterns in raw_patterns.items():
        if not isinstance(patterns, list):
            raise RuntimeError(f"Symbol patterns for {language} must be a list")

        compiled_patterns[str(language)] = []
        for entry in patterns:
            if not isinstance(entry, dict):
                raise RuntimeError(f"Symbol pattern entry for {language} must be an object")
            symbol_type = str(entry.get("type") or "").strip()
            pattern = str(entry.get("pattern") or "")
            raw_flags = entry.get("flags", [])
            if not isinstance(raw_flags, list):
                raise RuntimeError(f"Symbol pattern flags for {language}.{symbol_type} must be a list")
            if not symbol_type or not pattern:
                raise RuntimeError(f"Symbol pattern entry for {language} requires type and pattern")
            compiled_patterns[str(language)].append(
                (symbol_type, re.compile(pattern, compile_regex_flags([str(flag) for flag in raw_flags])))
            )
    return compiled_patterns


CODE_INDEX_CONFIG = load_json_config(CODE_INDEX_CONFIG_FILE)


# -----------------------------
# Ignore configuration
# -----------------------------

IGNORE_DIRS = config_string_set(CODE_INDEX_CONFIG, "ignore_dirs")
IGNORE_SUFFIXES = config_string_set(CODE_INDEX_CONFIG, "ignore_suffixes", lowercase=True)
LANG_BY_EXT = config_string_map(CODE_INDEX_CONFIG, "language_by_extension")


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


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def line_range_for_chunk(text: str, chunk_text: str, search_start: int) -> tuple[int, int, int]:
    start = text.find(chunk_text, search_start)
    if start < 0:
        start = text.find(chunk_text)
    if start < 0:
        return 1, max(1, chunk_text.count("\n") + 1), search_start

    end = start + len(chunk_text)
    line_start = text.count("\n", 0, start) + 1
    line_end = text.count("\n", 0, end) + 1
    return line_start, line_end, end


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


# -----------------------------
# Symbol extraction
# -----------------------------

SYMBOL_PATTERNS = config_symbol_patterns(CODE_INDEX_CONFIG)


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
    text = text.strip()

    if not text:
        return []

    symbols = extract_symbols(text, language)

    # If no symbols were found, fall back to normal overlapping text chunks.
    if not symbols:
        return [
            {
                "text": chunk,
                "symbol_type": "text_chunk",
                "symbol_name": None,
                "symbol_subchunk_index": 0,
            }
            for chunk in chunk_text(text)
        ]

    chunks: List[Dict[str, object]] = []

    # Include preamble/imports before first symbol as one chunk when useful.
    first_symbol_start = int(symbols[0]["start"])
    if first_symbol_start > 0:
        preamble = text[:first_symbol_start].strip()
        if preamble:
            for sub_index, sub_chunk in enumerate(chunk_text(preamble)):
                chunks.append(
                    {
                        "text": sub_chunk,
                        "symbol_type": "file_preamble",
                        "symbol_name": "file_preamble",
                        "symbol_subchunk_index": sub_index,
                    }
                )

    for i, symbol in enumerate(symbols):
        start = int(symbol["start"])
        end = int(symbols[i + 1]["start"]) if i + 1 < len(symbols) else len(text)

        symbol_text = text[start:end].strip()

        if not symbol_text:
            continue

        sub_chunks = chunk_text(symbol_text)

        for sub_index, sub_chunk in enumerate(sub_chunks):
            chunks.append(
                {
                    "text": sub_chunk,
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
    category = detect_category(file_path, language)
    text = read_file(file_path)

    if not text.strip():
        return 0

    chunks = chunk_text_with_symbols(text, language)

    if not chunks:
        return 0

    delete_existing_file_chunks(client, repo, relative_path)

    points = []
    search_start = 0
    indexed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    file_modified_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(file_path.stat().st_mtime))

    for chunk_index, chunk in enumerate(chunks):
        chunk_text_value = str(chunk.get("text") or "").strip()

        if not chunk_text_value:
            continue

        embedding = model.encode(chunk_text_value).tolist()
        line_start, line_end, search_start = line_range_for_chunk(text, chunk_text_value, search_start)
        chunk_content_hash = content_hash(chunk_text_value)
        chunk_id = f"{repo}:{relative_path}:{chunk_index}:{chunk_content_hash[:12]}"

        payload = {
            "chunk_id": chunk_id,
            "source_type": "code",
            "repo": repo,
            "repo_name": repo,
            "file": str(file_path),
            "file_path": relative_path,
            "relative_path": relative_path,
            "language": language,
            "category": category,
            "symbol_type": chunk.get("symbol_type"),
            "symbol_name": chunk.get("symbol_name"),
            "symbol_subchunk_index": chunk.get("symbol_subchunk_index", 0),
            "chunk_index": chunk_index,
            "line_start": line_start,
            "line_end": line_end,
            "content_hash": chunk_content_hash,
            "indexed_at": indexed_at,
            "file_modified_at": file_modified_at,
            "text": chunk_text_value,
        }

        points.append(
            PointStruct(
                id=stable_id(repo, relative_path, chunk_index),
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

    files = collect_files(target)

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


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python index_code.py ~/ai-stack/memory/code-memory/<repo-name>")
        print("  python index_code.py ~/ai-stack/memory/code-memory/<repo-name>/path/to/file.py")
        sys.exit(1)

    index_target(Path(sys.argv[1]))
