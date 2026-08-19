"""Transport-neutral document and chunk models used by the RAG pipeline."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Document:
    path: Path
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Chunk:
    text: str
    index: int
    metadata: dict[str, Any] = field(default_factory=dict)
