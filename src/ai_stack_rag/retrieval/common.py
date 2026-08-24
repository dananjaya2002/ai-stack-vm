"""Common retrieval result normalization."""

from typing import Any, Iterable


def dedupe_chunks(chunks: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for chunk in chunks:
        key = (
            chunk.get("source"),
            chunk.get("repo"),
            chunk.get("relative_path") or chunk.get("file"),
            chunk.get("chunk_index"),
        )
        if key not in seen:
            seen.add(key)
            result.append(chunk)
    return result


def payload(point: Any) -> dict[str, Any]:
    value = getattr(point, "payload", None) or {}
    return dict(value)
