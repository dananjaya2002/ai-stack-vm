"""Injectable memory retrieval service."""

from typing import Any


class MemoryRetriever:
    def __init__(self, store: Any, embedder: Any, top_k: int = 6) -> None:
        self.store, self.embedder, self.top_k = store, embedder, top_k

    def search(self, query: str) -> Any:
        return self.store.search(self.embedder.encode(query), self.top_k)
