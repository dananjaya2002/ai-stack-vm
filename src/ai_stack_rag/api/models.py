"""Shared request models for OpenAI-compatible RAG APIs."""

from typing import Literal, Optional

from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: Optional[str] = None
    messages: list[ChatMessage]
    temperature: Optional[float] = 0.2
    max_tokens: Optional[int] = 2048
    stream: Optional[bool] = False


class AskRequest(BaseModel):
    question: str


class SearchRequest(BaseModel):
    query: str
    source: Literal["code", "memory", "both"] = "both"
    top_k: Optional[int] = None
