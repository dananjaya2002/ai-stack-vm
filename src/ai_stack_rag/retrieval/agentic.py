"""Types and orchestration boundary for multi-step retrieval."""

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class RetrievalStep:
    source: str
    query: str


class AgenticRetriever:
    def __init__(self, search: Callable[[RetrievalStep], list[dict[str, Any]]]) -> None:
        self._search = search

    def run(self, steps: list[RetrievalStep]) -> list[dict[str, Any]]:
        return [chunk for step in steps for chunk in self._search(step)]
