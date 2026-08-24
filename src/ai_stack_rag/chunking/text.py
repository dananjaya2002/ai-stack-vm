"""Deterministic plain-text chunking."""

from ai_stack_rag.models import Chunk


def chunk_text(text: str, chunk_size: int = 500) -> list[str]:
    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")
    return [text[index:index + chunk_size] for index in range(0, len(text), chunk_size)]


def chunks(text: str, chunk_size: int = 500) -> list[Chunk]:
    return [Chunk(text=value, index=index) for index, value in enumerate(chunk_text(text, chunk_size))]
