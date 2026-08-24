import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ai_stack_rag.embeddings.provider import EmbeddingProvider


class EmbeddingProviderTests(unittest.TestCase):
    def test_rejects_unknown_device_before_loading_model(self):
        with self.assertRaisesRegex(ValueError, "cpu.*cuda"):
            EmbeddingProvider(device="mps")

    def test_passes_explicit_device_to_sentence_transformer(self):
        calls = []

        class FakeSentenceTransformer:
            def __init__(self, model_name, *, device):
                calls.append((model_name, device))

            def encode(self, _text):
                return [0.1, 0.2]

        module = types.ModuleType("sentence_transformers")
        module.SentenceTransformer = FakeSentenceTransformer
        previous = sys.modules.get("sentence_transformers")
        sys.modules["sentence_transformers"] = module
        try:
            provider = EmbeddingProvider("test-model", "cuda")
            self.assertEqual(provider.dimension(), 2)
        finally:
            if previous is None:
                del sys.modules["sentence_transformers"]
            else:
                sys.modules["sentence_transformers"] = previous

        self.assertEqual(calls, [("test-model", "cuda")])

    def test_encodes_multiple_texts_in_one_model_call(self):
        calls = []

        class FakeSentenceTransformer:
            def __init__(self, _model_name, *, device):
                self.device = device

            def encode(self, texts):
                calls.append(texts)
                return [[0.1, 0.2], [0.3, 0.4]]

        module = types.ModuleType("sentence_transformers")
        module.SentenceTransformer = FakeSentenceTransformer
        previous = sys.modules.get("sentence_transformers")
        sys.modules["sentence_transformers"] = module
        try:
            provider = EmbeddingProvider("test-model", "cpu")
            vectors = provider.encode_many(["first", "second"])
        finally:
            if previous is None:
                del sys.modules["sentence_transformers"]
            else:
                sys.modules["sentence_transformers"] = previous

        self.assertEqual(calls, [["first", "second"]])
        self.assertEqual(vectors, [[0.1, 0.2], [0.3, 0.4]])

if __name__ == "__main__":
    unittest.main()
