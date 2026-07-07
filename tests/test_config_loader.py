import importlib.util
import re
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG_LOADER_PATH = ROOT / "scripts" / "shared" / "config_loader.py"
SPEC = importlib.util.spec_from_file_location("config_loader", CONFIG_LOADER_PATH)
config_loader = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(config_loader)


class ConfigLoaderTests(unittest.TestCase):
    def test_load_json_object_requires_object(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text('{"enabled": true}', encoding="utf-8")
            self.assertEqual(config_loader.load_json_object(path, "demo"), {"enabled": True})

            path.write_text('["not", "object"]', encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "must be a JSON object"):
                config_loader.load_json_object(path, "demo")

    def test_require_string_set_trims_and_lowercases(self):
        result = config_loader.require_string_set(
            {"extensions": [" .PY ", "", ".MD"]},
            "extensions",
            "code",
            lowercase=True,
        )
        self.assertEqual(result, {".py", ".md"})

    def test_require_string_map_normalizes_keys(self):
        result = config_loader.require_string_map(
            {"aliases": {" Python ": "py", "": "skip"}},
            "aliases",
            "code",
        )
        self.assertEqual(result, {"python": "py"})

    def test_compile_regex_flags_rejects_unknown_flag(self):
        self.assertEqual(config_loader.compile_regex_flags(["IGNORECASE"], "code"), re.IGNORECASE)
        with self.assertRaisesRegex(RuntimeError, "Unsupported regex flag"):
            config_loader.compile_regex_flags(["NO_SUCH_FLAG"], "code")

    def test_require_symbol_patterns_compiles_patterns(self):
        patterns = config_loader.require_symbol_patterns(
            {
                "symbol_patterns": {
                    "python": [
                        {"type": "function", "pattern": r"^def\s+(\w+)", "flags": ["MULTILINE"]}
                    ]
                }
            },
            "symbol_patterns",
            "code",
        )
        symbol_type, pattern = patterns["python"][0]
        self.assertEqual(symbol_type, "function")
        self.assertIsNotNone(pattern.search("def example():\n    pass"))


if __name__ == "__main__":
    unittest.main()
