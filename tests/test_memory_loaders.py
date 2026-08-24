import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ai_stack_rag.ingestion.loaders import iter_memory_files, load_document


class MemoryLoaderTests(unittest.TestCase):
    def test_pdf_files_are_discovered(self):
        with tempfile.TemporaryDirectory() as directory:
            pdf_path = Path(directory) / "memory.pdf"
            pdf_path.touch()
            self.assertEqual(iter_memory_files(Path(directory)), [pdf_path])

    @patch("ai_stack_rag.ingestion.loaders.PdfReader")
    def test_pdf_text_is_extracted(self, reader: MagicMock):
        reader.return_value.pages = [
            MagicMock(extract_text=MagicMock(return_value="First page")),
            MagicMock(extract_text=MagicMock(return_value="Second page")),
        ]
        with tempfile.TemporaryDirectory() as directory:
            pdf_path = Path(directory) / "memory.pdf"
            pdf_path.touch()
            document = load_document(pdf_path)

        self.assertIsNotNone(document)
        self.assertEqual(document.text, "First page\n\nSecond page")
        self.assertEqual(document.metadata["file_name"], "memory.pdf")


if __name__ == "__main__":
    unittest.main()
