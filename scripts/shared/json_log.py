import json
from pathlib import Path
from typing import Any, Dict, Optional


def append_json_event(path: Path, entry: Dict[str, Any]) -> Optional[str]:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return None
    except Exception as exc:
        return str(exc)
