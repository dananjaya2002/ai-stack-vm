"""Injectable code retrieval service."""

from typing import Any


class CodeRetriever:
    def __init__(self, store: Any, embedder: Any, top_k: int = 6) -> None:
        self.store, self.embedder, self.top_k = store, embedder, top_k

    def search(self, query: str, query_filter: Any = None) -> Any:
        return self.store.search(self.embedder.encode(query), self.top_k, query_filter)
