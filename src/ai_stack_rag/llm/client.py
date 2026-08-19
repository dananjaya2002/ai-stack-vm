"""Injectable OpenAI-compatible chat client."""

from typing import Any

import requests


class OpenAICompatibleClient:
    def __init__(self, base_url: str, model: str, timeout: int = 300, session: Any = requests) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.session = session

    def chat(self, messages: list[dict[str, str]], **options: Any) -> str:
        payload = {"model": self.model, "messages": messages, "stream": False, **options}
        response = self.session.post(f"{self.base_url}/chat/completions", json=payload, timeout=self.timeout)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
