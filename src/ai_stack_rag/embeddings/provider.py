"""Lazy SentenceTransformer provider."""

from threading import Lock
from typing import Any


class EmbeddingProvider:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2", device: str = "cpu") -> None:
        if device not in {"cpu", "cuda"}:
            raise ValueError("Embedding device must be 'cpu' or 'cuda'")
        self.model_name = model_name
        self.device = device
        self._model: Any = None
        self._lock = Lock()

    def _get_model(self) -> Any:
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from sentence_transformers import SentenceTransformer
                    self._model = SentenceTransformer(self.model_name, device=self.device)
        return self._model

    def encode(self, text: str) -> list[float]:
        encoded = self._get_model().encode(text)
        return encoded.tolist() if hasattr(encoded, "tolist") else list(encoded)

    def encode_many(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        encoded = self._get_model().encode(texts)
        rows = encoded.tolist() if hasattr(encoded, "tolist") else list(encoded)
        return [
            row.tolist() if hasattr(row, "tolist") else list(row)
            for row in rows
        ]

    def dimension(self) -> int:
        return len(self.encode("vector-size-test"))
