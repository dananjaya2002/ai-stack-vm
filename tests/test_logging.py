import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.shared.json_log import append_json_event
from scripts.shared.log_status import log_stats, read_last_lines


class LogStatusTests(unittest.TestCase):
    def test_disabled_log_is_reported_explicitly(self):
        with tempfile.TemporaryDirectory() as tmp:
            status = log_stats(Path(tmp) / "missing.log", enabled=False)
        self.assertEqual(status["state"], "disabled")
        self.assertTrue(status["ok"])
        self.assertFalse(status["enabled"])

    def test_enabled_missing_log_is_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            status = log_stats(Path(tmp) / "missing.log", enabled=True)
        self.assertEqual(status["state"], "unavailable")
        self.assertFalse(status["exists"])

    def test_empty_and_available_logs_are_distinct(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.log"
            path.touch()
            self.assertEqual(log_stats(path)["state"], "empty")
            path.write_text("first\nsecond\n", encoding="utf-8")
            self.assertEqual(log_stats(path)["state"], "available")
            response = read_last_lines(path, "code", max_lines=1)
        self.assertEqual(response["source"], "code")
        self.assertEqual(response["lines"], ["second"])

    def test_unreadable_log_is_unavailable(self):
        path = Path("events.log")
        with patch.object(Path, "read_text", side_effect=PermissionError("denied")):
            with patch.object(Path, "exists", return_value=True):
                response = read_last_lines(path, "memory")
        self.assertEqual(response["state"], "unavailable")
        self.assertIn("denied", response["error"])


class JsonLogTests(unittest.TestCase):
    def test_startup_event_creates_parent_and_valid_json_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested" / "proxy.log"
            error = append_json_event(path, {"type": "proxy_started", "service": "memory-proxy"})
            event = json.loads(path.read_text(encoding="utf-8"))
        self.assertIsNone(error)
        self.assertEqual(event["type"], "proxy_started")

    def test_logging_failure_is_non_fatal(self):
        with tempfile.TemporaryDirectory() as tmp:
            error = append_json_event(Path(tmp), {"event": "proxy_started"})
        self.assertIsNotNone(error)


if __name__ == "__main__":
    unittest.main()
