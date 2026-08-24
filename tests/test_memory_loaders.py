import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ai_stack_rag.ingestion.loaders import iter_memory_files, load_document


class MemoryLoaderTests(unittest.TestCase):
    def test_only_markdown_files_are_discovered(self):
        with tempfile.TemporaryDirectory() as directory:
            markdown_path = Path(directory) / "memory.md"
            markdown_path.write_text("Engineering memory", encoding="utf-8")
            (Path(directory) / "memory.pdf").touch()
            (Path(directory) / "memory.txt").touch()
            self.assertEqual(iter_memory_files(Path(directory)), [markdown_path])

    def test_markdown_text_is_loaded(self):
        with tempfile.TemporaryDirectory() as directory:
            markdown_path = Path(directory) / "memory.md"
            markdown_path.write_text("# Memory\n\nUseful detail.", encoding="utf-8")
            document = load_document(markdown_path)

        self.assertIsNotNone(document)
        self.assertEqual(document.text, "# Memory\n\nUseful detail.")
        self.assertEqual(document.metadata["file_name"], "memory.md")


if __name__ == "__main__":
    unittest.main()
