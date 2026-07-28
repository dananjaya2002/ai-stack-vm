import unittest

from scripts.shared.source_locations import (
    canonical_source_path,
    clean_source_markers,
    format_source_location,
)


class SourceLocationTests(unittest.TestCase):
    def test_normalizes_windows_repo_relative_path(self):
        self.assertEqual(
            canonical_source_path(
                "code",
                repo_name="example",
                relative_path=r"src\service\api.py",
            ),
            "example/src/service/api.py",
        )

    def test_normalizes_legacy_absolute_path(self):
        self.assertEqual(
            canonical_source_path(
                "code",
                repo_name="example",
                file_path="/code-memory/example/src/api.py",
            ),
            "example/src/api.py",
        )

    def test_hides_absolute_path_without_repo_component(self):
        self.assertEqual(
            canonical_source_path(
                "code",
                repo_name="example",
                file_path=r"C:\Users\person\private\api.py",
            ),
            "example/api.py",
        )

    def test_removes_duplicate_repo_prefixes(self):
        self.assertEqual(
            canonical_source_path(
                "code",
                repo_name="example",
                relative_path="example/example/src/api.py",
            ),
            "example/src/api.py",
        )

    def test_formats_code_line_range(self):
        self.assertEqual(
            format_source_location(
                "code",
                repo_name="example",
                relative_path="src/api.py",
                line_start=10,
                line_end=18,
            ),
            "example/src/api.py:10-18",
        )

    def test_memory_location_is_filename_only(self):
        self.assertEqual(
            format_source_location(
                "memory",
                file_path="/memory/teams/platform/architecture.md",
                line_start=10,
                line_end=18,
            ),
            "architecture.md",
        )

    def test_replaces_numbered_marker_and_removes_numbered_section(self):
        answer = (
            "The API is defined here [Source 1].\n\n"
            "Sources:\n- [Source 1] placeholder"
        )
        cleaned = clean_source_markers(answer, ["example/src/api.py:10-18"])
        self.assertEqual(
            cleaned,
            "The API is defined here `example/src/api.py:10-18`.",
        )
        self.assertNotIn("[Source", cleaned)


if __name__ == "__main__":
    unittest.main()
