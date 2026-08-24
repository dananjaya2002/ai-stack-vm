"""Filesystem loaders without model or database dependencies."""

from pathlib import Path
from typing import Iterable

from pypdf import PdfReader

from ai_stack_rag.models import Document


MEMORY_SUFFIXES = frozenset({".md", ".txt", ".pdf", ".py", ".json", ".yaml", ".yml"})


def iter_memory_files(root: Path, suffixes: Iterable[str] = MEMORY_SUFFIXES) -> list[Path]:
    allowed = {suffix.lower() for suffix in suffixes}
    if not root.exists():
        return []
    return sorted(path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in allowed)


def load_document(path: Path) -> Document | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        if path.suffix.lower() == ".pdf":
            reader = PdfReader(path)
            text = "\n\n".join(page_text for page in reader.pages if (page_text := page.extract_text()))
        else:
            text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None
    if not text.strip():
        return None
    return Document(path=path, text=text, metadata={"file_name": path.name.lower()})
