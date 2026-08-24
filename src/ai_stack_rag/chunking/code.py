"""Language detection and symbol-aware source-code chunking."""

import hashlib
import re
from pathlib import Path
from typing import Any, Iterable, Mapping, Pattern


LOCK_FILES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock"}


def should_ignore(path: Path, ignore_dirs: Iterable[str], ignore_suffixes: Iterable[str]) -> bool:
    if set(path.parts).intersection(ignore_dirs):
        return True
    if path.suffix.lower() in ignore_suffixes or path.name.startswith(".env"):
        return True
    return path.name in LOCK_FILES


def detect_language(path: Path, language_by_extension: Mapping[str, str]) -> str:
    name = path.name.lower()
    if name == "dockerfile" or name.endswith(".dockerfile"):
        return "dockerfile"
    return language_by_extension.get(path.suffix.lower(), "text")


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
    digest = hashlib.sha256(f"{repo}:{relative_path}:{chunk_index}".encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def chunk_text_spans(
    text: str,
    max_chars: int = 2200,
    overlap_chars: int = 300,
    base_offset: int = 0,
) -> list[dict[str, Any]]:
    if not text.strip():
        return []
    if max_chars < 1 or overlap_chars < 0 or overlap_chars >= max_chars:
        raise ValueError("chunk sizes must satisfy 0 <= overlap_chars < max_chars")
    result: list[dict[str, Any]] = []
    content_start = len(text) - len(text.lstrip())
    content_end = len(text.rstrip())
    start = content_start
    while start < content_end:
        end = min(start + max_chars, content_end)
        if end < content_end:
            newline = text.rfind("\n", start, end)
            if newline > start + 500:
                end = newline
        raw = text[start:end]
        left_trim = len(raw) - len(raw.lstrip())
        right_trim = len(raw.rstrip())
        value = raw[left_trim:right_trim]
        if value:
            result.append({
                "text": value,
                "char_start": base_offset + start + left_trim,
                "char_end": base_offset + start + right_trim,
            })
        if end >= content_end:
            break
        start = max(content_start, end - overlap_chars)
    return result


def extract_symbols(
    text: str,
    language: str,
    symbol_patterns: Mapping[str, list[tuple[str, Pattern[str]]]],
) -> list[dict[str, Any]]:
    symbols: list[dict[str, Any]] = []
    if language == "markdown":
        for match in re.finditer(r"^(#{1,6})\s+(.+)$", text, re.MULTILINE):
            symbols.append({"symbol_type": "markdown_section", "symbol_name": match.group(2).strip(), "start": match.start()})
        return symbols
    for symbol_type, pattern in symbol_patterns.get(language, []):
        for match in pattern.finditer(text):
            name = f"app.{match.group(1)}" if symbol_type == "fastapi_route" else (match.group(1) if match.groups() else symbol_type)
            symbols.append({"symbol_type": symbol_type, "symbol_name": name, "start": match.start()})
    return sorted(symbols, key=lambda item: int(item["start"]))


def chunk_text_with_symbols(
    text: str,
    language: str,
    symbol_patterns: Mapping[str, list[tuple[str, Pattern[str]]]],
    max_chars: int = 2200,
    overlap_chars: int = 300,
) -> list[dict[str, Any]]:
    if not text:
        return []
    symbols = extract_symbols(text, language, symbol_patterns)
    if not symbols:
        plain = chunk_text_spans(text, max_chars, overlap_chars)
        for chunk in plain:
            chunk.update({"symbol_type": "text_chunk", "symbol_name": None, "symbol_subchunk_index": 0})
        return plain
    result: list[dict[str, Any]] = []
    first_start = int(symbols[0]["start"])
    if text[:first_start].strip():
        for sub_index, chunk in enumerate(chunk_text_spans(text[:first_start], max_chars, overlap_chars)):
            result.append({**chunk, "symbol_type": "file_preamble", "symbol_name": "file_preamble", "symbol_subchunk_index": sub_index})
    for index, symbol in enumerate(symbols):
        start = int(symbol["start"])
        end = int(symbols[index + 1]["start"]) if index + 1 < len(symbols) else len(text)
        for sub_index, chunk in enumerate(chunk_text_spans(text[start:end], max_chars, overlap_chars, start)):
            result.append({**chunk, "symbol_type": symbol["symbol_type"], "symbol_name": symbol["symbol_name"], "symbol_subchunk_index": sub_index})
    return result
