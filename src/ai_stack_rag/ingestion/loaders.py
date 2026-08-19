"""Filesystem loaders without model or database dependencies."""

from pathlib import Path
from typing import Iterable

from ai_stack_rag.models import Document


MEMORY_SUFFIXES = frozenset({".md", ".txt", ".py", ".json", ".yaml", ".yml"})


def iter_memory_files(root: Path, suffixes: Iterable[str] = MEMORY_SUFFIXES) -> list[Path]:
    allowed = {suffix.lower() for suffix in suffixes}
    if not root.exists():
        return []
    return sorted(path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in allowed)


def load_document(path: Path) -> Document | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    return Document(path=path, text=text, metadata={"file_name": path.name.lower()})
