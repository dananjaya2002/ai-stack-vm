"""Service application selection for development tooling."""

from fastapi import FastAPI


def create_app(service: str = "agentic") -> FastAPI:
    if service == "memory":
        from ai_stack_rag.api.memory import create_app as factory
    elif service == "code":
        from ai_stack_rag.api.code import create_app as factory
    elif service == "agentic":
        from ai_stack_rag.api.agentic import create_app as factory
    else:
        raise ValueError(f"Unknown RAG service: {service}")
    return factory()
