import os
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai_stack_rag.chunking.code import chunk_text_spans, stable_id
from ai_stack_rag.chunking.text import chunk_text
from ai_stack_rag.prompts.templates import code_answer, memory_answer
from ai_stack_rag.retrieval.common import dedupe_chunks
from ai_stack_rag.utils.config import load_settings


class ConfigurationTests(unittest.TestCase):
    def test_environment_overrides_explicit_yaml_and_root_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "override.yaml"
            path.write_text("vector_db:\n  port: 7000\nchunking:\n  memory_size: 250\n", encoding="utf-8")
            settings = load_settings(path, {"QDRANT_PORT": "7444"})
        self.assertEqual(settings.vector_db.port, 7444)
        self.assertEqual(settings.chunking.memory_size, 250)
        self.assertEqual(settings.vector_db.code_collection, "code-memory")

    def test_invalid_environment_value_is_clear(self):
        with self.assertRaisesRegex(ValueError, "QDRANT_PORT"):
            load_settings(environ={"QDRANT_PORT": "not-a-port"})

    def test_embedding_device_environment_override_is_validated(self):
        self.assertEqual(load_settings(environ={"EMBEDDING_DEVICE": "cuda"}).embeddings.device, "cuda")
        with self.assertRaisesRegex(ValueError, "embeddings.device"):
            load_settings(environ={"EMBEDDING_DEVICE": "metal"})


class PipelineContractTests(unittest.TestCase):
    def test_memory_chunks_keep_exact_boundaries(self):
        self.assertEqual(chunk_text("abcdefgh", 3), ["abc", "def", "gh"])

    def test_code_chunks_overlap_without_losing_content(self):
        result = chunk_text_spans("a" * 2500, max_chars=2200, overlap_chars=300)
        self.assertEqual(result[0]["char_start"], 0)
        self.assertEqual(result[1]["char_start"], 1900)
        self.assertEqual(result[-1]["char_end"], 2500)

    def test_stable_ids_retain_existing_algorithm(self):
        self.assertEqual(stable_id("repo", "src/app.py", 2), stable_id("repo", "src/app.py", 2))
        self.assertNotEqual(stable_id("repo", "src/app.py", 2), stable_id("repo", "src/app.py", 3))

    def test_deduplication_preserves_first_result(self):
        chunks = [
            {"source": "code", "relative_path": "a.py", "chunk_index": 1, "score": 0.9},
            {"source": "code", "relative_path": "a.py", "chunk_index": 1, "score": 0.8},
        ]
        self.assertEqual(dedupe_chunks(chunks), [chunks[0]])

    def test_named_prompts_include_context_and_question(self):
        self.assertIn("memory context", memory_answer("why?", "facts"))
        self.assertIn("source references", code_answer("where?", "code"))


class OrganizedLayoutTests(unittest.TestCase):
    def test_legacy_service_directories_are_removed(self):
        legacy = ["memory-proxy", "code-proxy", "agentic-rag", "watcher", "shared", "config"]
        self.assertTrue(all(not (ROOT / "scripts" / name).exists() for name in legacy))

    def test_package_entry_points_are_present(self):
        expected = [
            "src/ai_stack_rag/api/memory.py",
            "src/ai_stack_rag/api/code.py",
            "src/ai_stack_rag/api/agentic.py",
            "src/ai_stack_rag/ingestion/memory.py",
            "src/ai_stack_rag/ingestion/code.py",
        ]
        self.assertTrue(all((ROOT / path).is_file() for path in expected))

    def test_public_routes_remain_declared(self):
        sources = "\n".join(
            (ROOT / path).read_text(encoding="utf-8")
            for path in [
                "src/ai_stack_rag/api/memory.py",
                "src/ai_stack_rag/api/code.py",
                "src/ai_stack_rag/api/agentic.py",
            ]
        )
        for route in ["/v1/models", "/v1/chat/completions", "/search", "/ask", "/v1/rag/debug"]:
            self.assertIn(f'"{route}"', sources)


if __name__ == "__main__":
    unittest.main()
