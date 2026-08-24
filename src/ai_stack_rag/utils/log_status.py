"""Log status and tail helpers."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


def _iso_time(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def log_stats(path: Path, enabled: bool = True) -> Dict[str, Any]:
    if not enabled:
        return {
            "ok": True, "warning": True, "error": None, "state": "disabled",
            "enabled": False, "path": str(path), "exists": path.exists(),
            "size_bytes": 0, "latest_modified_time": None,
        }
    if not path.exists():
        return {
            "ok": False, "warning": True,
            "error": "Logging is enabled, but the log file is unavailable.",
            "state": "unavailable", "enabled": True, "path": str(path),
            "exists": False, "size_bytes": 0, "latest_modified_time": None,
        }
    try:
        stat = path.stat()
        return {
            "ok": True, "warning": stat.st_size == 0, "error": None,
            "state": "empty" if stat.st_size == 0 else "available",
            "enabled": True, "path": str(path), "exists": True,
            "size_bytes": stat.st_size, "latest_modified_time": _iso_time(stat.st_mtime),
        }
    except Exception as exc:
        return {
            "ok": False, "warning": True, "error": str(exc),
            "state": "unavailable", "enabled": True, "path": str(path),
            "exists": True, "size_bytes": None, "latest_modified_time": None,
        }


def read_last_lines(path: Path, source: str, enabled: bool = True, max_lines: int = 400) -> Dict[str, Any]:
    if not enabled:
        return {
            "ok": True, "error": None, "source": source, "state": "disabled",
            "enabled": False, "path": str(path), "lines": [],
        }
    if not path.exists():
        return {
            "ok": False, "error": "Logging is enabled, but the log file is unavailable.",
            "source": source, "state": "unavailable", "enabled": True,
            "path": str(path), "lines": [],
        }
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return {
            "ok": True, "error": None, "source": source,
            "state": "available" if lines else "empty", "enabled": True,
            "path": str(path), "lines": lines[-max_lines:],
        }
    except Exception as exc:
        return {
            "ok": False, "error": str(exc), "source": source,
            "state": "unavailable", "enabled": True, "path": str(path), "lines": [],
        }
