import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ai_stack_rag.utils.document_refs import extract_document_filename
from ai_stack_rag.llm.openai_compat import _stream_events


class FakeResponse:
    def __init__(self, lines):
        self.lines = lines
        self.closed = False

    def iter_lines(self, decode_unicode=False):
        return iter(self.lines)

    def close(self):
        self.closed = True


class DocumentReferenceTests(unittest.TestCase):
    def test_extracts_unquoted_filename(self):
        question = "List all commands from Customized PowerShell commands.md and explain them."
        self.assertEqual(extract_document_filename(question), "Customized PowerShell commands.md")

    def test_extracts_quoted_filename_case_insensitively(self):
        self.assertEqual(
            extract_document_filename('Summarize "RunBook.MD"'),
            "RunBook.MD",
        )

    def test_returns_none_without_document_reference(self):
        self.assertIsNone(extract_document_filename("Explain the deployment process"))


class StreamingCompatibilityTests(unittest.TestCase):
    def test_decodes_utf8_stream_bytes_without_mojibake(self):
        upstream = {
            "choices": [{"index": 0, "delta": {"content": "📋 HTML Structure ✅"}}],
        }
        line = f"data: {json.dumps(upstream, ensure_ascii=False)}".encode("utf-8")
        response = FakeResponse([line, b"data: [DONE]"])

        events = list(_stream_events(response, "proxy-emoji", "memory-proxy"))

        chunk = json.loads(events[0][len("data: "):])
        self.assertEqual(chunk["choices"][0]["delta"]["content"], "📋 HTML Structure ✅")
        self.assertTrue(response.closed)

    def test_rewrites_chunk_identity_and_finishes_stream(self):
        upstream = {
            "id": "upstream",
            "model": "llama",
            "choices": [{"index": 0, "delta": {"content": "Hello"}}],
        }
        response = FakeResponse([f"data: {json.dumps(upstream)}", "data: [DONE]"])
        events = list(_stream_events(response, "proxy-1", "agentic-rag"))
        chunk = json.loads(events[0][len("data: "):])
        self.assertEqual(chunk["id"], "proxy-1")
        self.assertEqual(chunk["model"], "agentic-rag")
        self.assertEqual(events[-1], "data: [DONE]\n\n")
        self.assertTrue(response.closed)

    def test_transforms_content_split_across_stream_events(self):
        first = {
            "choices": [{"index": 0, "delta": {"content": "See [Sour"}}],
        }
        second = {
            "choices": [{"index": 0, "delta": {"content": "ce 1]."}}],
        }
        response = FakeResponse(
            [
                f"data: {json.dumps(first)}",
                f"data: {json.dumps(second)}",
                "data: [DONE]",
            ]
        )
        events = list(
            _stream_events(
                response,
                "proxy-1",
                "code-proxy",
                lambda content: content.replace("[Source 1]", "`repo/file.py`"),
            )
        )
        chunk = json.loads(events[0][len("data: "):])
        self.assertEqual(
            chunk["choices"][0]["delta"]["content"],
            "See `repo/file.py`.",
        )
        self.assertTrue(response.closed)


if __name__ == "__main__":
    unittest.main()
