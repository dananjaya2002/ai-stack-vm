"""Small Qdrant adapter used by indexing and retrieval components."""

from typing import Any, Iterable


class QdrantStore:
    def __init__(self, host: str, port: int, collection: str, client: Any = None) -> None:
        if client is None:
            from qdrant_client import QdrantClient
            client = QdrantClient(host=host, port=port)
        self.client = client
        self.collection = collection

    def ensure_collection(self, vector_size: int) -> None:
        from qdrant_client.models import Distance, VectorParams
        existing = {item.name for item in self.client.get_collections().collections}
        if self.collection not in existing:
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )

    def upsert(self, points: Iterable[Any], wait: bool = True) -> None:
        self.client.upsert(collection_name=self.collection, points=list(points), wait=wait)

    def delete(self, selector: Any, wait: bool = True) -> None:
        self.client.delete(collection_name=self.collection, points_selector=selector, wait=wait)

    def search(self, vector: list[float], limit: int, query_filter: Any = None) -> Any:
        return self.client.query_points(
            collection_name=self.collection,
            query=vector,
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
        ).points
