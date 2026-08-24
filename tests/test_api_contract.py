import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class APIContractTests(unittest.TestCase):
    def _load_routes(self, module_name: str) -> set[str]:
        with tempfile.TemporaryDirectory() as directory:
            env = {
                "SECURITY_MODE": "development",
                "LLM_BASE_URL": "http://llama.test/v1",
                "LLM_MODEL": "test-model.gguf",
                "QDRANT_HOST": "qdrant.test",
                "QDRANT_PORT": "6333",
                "QDRANT_COLLECTION": "test-collection",
                "MEMORY_COLLECTION": "test-memory",
                "CODE_COLLECTION": "test-code",
                "MEMORY_DIR": directory,
                "REPOS_ROOT": directory,
                "AGENTIC_RAG_LOG_FILE": str(Path(directory) / "agentic.log"),
                "MEMORY_API_LOG_FILE": str(Path(directory) / "memory.log"),
                "CODE_PROXY_LOG_FILE": str(Path(directory) / "code.log"),
            }
            with patch.dict(os.environ, env), patch("qdrant_client.QdrantClient"):
                sys.modules.pop(module_name, None)
                module = importlib.import_module(module_name)
        return {route.path for route in module.app.routes}

    def test_memory_routes_are_compatible(self):
        routes = self._load_routes("ai_stack_rag.api.memory")
        self.assertTrue({"/ask", "/search", "/v1/models", "/v1/chat/completions"} <= routes)

    def test_code_routes_are_compatible(self):
        routes = self._load_routes("ai_stack_rag.api.code")
        self.assertTrue({"/ask", "/search", "/v1/models", "/v1/chat/completions"} <= routes)

    def test_agentic_routes_are_compatible(self):
        routes = self._load_routes("ai_stack_rag.api.agentic")
        self.assertTrue(
            {"/ask", "/search", "/v1/models", "/v1/rag/debug", "/v1/chat/completions"}
            <= routes
        )


if __name__ == "__main__":
    unittest.main()
