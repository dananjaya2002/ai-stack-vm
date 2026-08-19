"""Default AI Stack RAG application entry point.

The existing memory, code, and agentic service entry points remain supported.
This module exposes the agentic RAG application as the combined/default entry.
"""

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from ai_stack_rag.api.agentic import app  # noqa: E402

__all__ = ["app"]
