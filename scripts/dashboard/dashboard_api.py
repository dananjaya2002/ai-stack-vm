import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import psutil
import requests
from dotenv import load_dotenv
from fastapi import FastAPI


load_dotenv()
load_dotenv(Path(__file__).with_name("dashboard.env"), override=False)

LLAMA_BASE_URL = os.getenv("LLAMA_BASE_URL", "http://localhost:8082/v1").rstrip("/")
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333").rstrip("/")
ENGINEERING_MEMORY_DIR = Path(
    os.getenv("ENGINEERING_MEMORY_DIR", str(Path.home() / "ai-stack/memory/engineering-memory"))
)
CODE_MEMORY_DIR = Path(os.getenv("CODE_MEMORY_DIR", str(Path.home() / "ai-stack/memory/code-memory")))
MEMORY_LOG = Path(os.getenv("MEMORY_LOG", str(Path.home() / "ai-stack/logs/memory_api.log")))
CODE_LOG = Path(os.getenv("CODE_LOG", str(Path.home() / "ai-stack/logs/code_proxy.log")))

HTTP_TIMEOUT_SECONDS = float(os.getenv("DASHBOARD_HTTP_TIMEOUT_SECONDS", "3"))

app = FastAPI(title="AI Stack Dashboard API")


def iso_time(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def error_payload(message: str, **extra: Any) -> Dict[str, Any]:
    return {"ok": False, "error": message, **extra}


def get_json(url: str) -> Dict[str, Any]:
    started = time.perf_counter()
    response = requests.get(url, timeout=HTTP_TIMEOUT_SECONDS)
    latency_ms = round((time.perf_counter() - started) * 1000, 2)
    response.raise_for_status()
    try:
        body: Any = response.json()
    except ValueError:
        body = response.text[:500]
    return {"latency_ms": latency_ms, "body": body, "status_code": response.status_code}


def first_llama_model(models_body: Any) -> Optional[str]:
    if not isinstance(models_body, dict):
        return None
    data = models_body.get("data")
    if not isinstance(data, list) or not data:
        return None
    first = data[0]
    if isinstance(first, dict):
        model_id = first.get("id")
        if isinstance(model_id, str) and model_id:
            return model_id
    return None


def extract_token_speed(response_body: Dict[str, Any], latency_ms: float) -> Dict[str, Any]:
    timings = response_body.get("timings")
    if isinstance(timings, dict):
        predicted_n = timings.get("predicted_n")
        predicted_ms = timings.get("predicted_ms")
        if predicted_n and predicted_ms:
            return {
                "tokens_per_second": round(float(predicted_n) / (float(predicted_ms) / 1000), 2),
                "source": "llama.cpp timings",
                "note": None,
            }

    usage = response_body.get("usage")
    if isinstance(usage, dict):
        completion_tokens = usage.get("completion_tokens")
        if completion_tokens and latency_ms > 0:
            return {
                "tokens_per_second": round(float(completion_tokens) / (latency_ms / 1000), 2),
                "source": "completion_tokens / wall latency",
                "note": "Approximate wall-clock estimate; llama.cpp timing fields were not present.",
            }

    return {
        "tokens_per_second": None,
        "source": None,
        "note": "Token speed unavailable; llama.cpp did not return timing or completion token fields.",
    }


def check_llama() -> Dict[str, Any]:
    try:
        models = get_json(f"{LLAMA_BASE_URL}/models")
    except Exception as exc:
        return error_payload(
            str(exc),
            base_url=LLAMA_BASE_URL,
            latency_ms=None,
            approximate_token_speed=None,
        )

    model_id = first_llama_model(models["body"]) or os.getenv("LLAMA_MODEL", "local-model")
    result: Dict[str, Any] = {
        "ok": True,
        "error": None,
        "base_url": LLAMA_BASE_URL,
        "latency_ms": models["latency_ms"],
        "model": model_id,
        "approximate_token_speed": {
            "tokens_per_second": None,
            "source": None,
            "note": "Token speed check was not attempted.",
        },
    }

    try:
        started = time.perf_counter()
        response = requests.post(
            f"{LLAMA_BASE_URL}/chat/completions",
            json={
                "model": model_id,
                "messages": [{"role": "user", "content": "Reply with: ok"}],
                "max_tokens": 8,
                "temperature": 0,
                "stream": False,
            },
            timeout=max(HTTP_TIMEOUT_SECONDS, 10),
        )
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        response.raise_for_status()
        response_body = response.json()
        result["chat_latency_ms"] = latency_ms
        result["approximate_token_speed"] = extract_token_speed(response_body, latency_ms)
    except Exception as exc:
        result["approximate_token_speed"] = {
            "tokens_per_second": None,
            "source": None,
            "note": f"Token speed check failed: {exc}",
        }

    return result


def check_qdrant() -> Dict[str, Any]:
    errors = []
    for path in ("/healthz", "/"):
        url = f"{QDRANT_URL}{path}"
        try:
            response = get_json(url)
            return {
                "ok": True,
                "error": None,
                "url": url,
                "latency_ms": response["latency_ms"],
                "status_code": response["status_code"],
            }
        except Exception as exc:
            errors.append(f"{url}: {exc}")

    return error_payload("; ".join(errors), url=QDRANT_URL, latency_ms=None)


def memory_stats(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return error_payload("Directory does not exist.", path=str(path), file_count=0, latest_modified_time=None)
    if not path.is_dir():
        return error_payload("Path exists but is not a directory.", path=str(path), file_count=0, latest_modified_time=None)

    file_count = 0
    latest_modified: Optional[float] = None
    try:
        for item in path.rglob("*"):
            if not item.is_file():
                continue
            file_count += 1
            modified = item.stat().st_mtime
            latest_modified = modified if latest_modified is None else max(latest_modified, modified)
    except Exception as exc:
        return error_payload(str(exc), path=str(path), file_count=file_count, latest_modified_time=None)

    return {
        "ok": True,
        "error": None,
        "path": str(path),
        "file_count": file_count,
        "latest_modified_time": iso_time(latest_modified) if latest_modified else None,
    }


def log_stats(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {
            "ok": False,
            "error": "Log file does not exist.",
            "path": str(path),
            "exists": False,
            "size_bytes": 0,
            "latest_modified_time": None,
        }
    try:
        stat = path.stat()
        return {
            "ok": True,
            "error": None,
            "path": str(path),
            "exists": True,
            "size_bytes": stat.st_size,
            "latest_modified_time": iso_time(stat.st_mtime),
        }
    except Exception as exc:
        return error_payload(str(exc), path=str(path), exists=True, size_bytes=None, latest_modified_time=None)


def system_stats() -> Dict[str, Any]:
    try:
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        return {
            "ok": True,
            "error": None,
            "cpu": {
                "usage_percent": psutil.cpu_percent(interval=0.1),
                "count": psutil.cpu_count(),
            },
            "ram": {
                "usage_percent": memory.percent,
                "total_bytes": memory.total,
                "available_bytes": memory.available,
                "used_bytes": memory.used,
            },
            "disk": {
                "path": "/",
                "usage_percent": disk.percent,
                "total_bytes": disk.total,
                "free_bytes": disk.free,
                "used_bytes": disk.used,
            },
        }
    except Exception as exc:
        return error_payload(str(exc))


@app.get("/api/dashboard/status")
def dashboard_status() -> Dict[str, Any]:
    llama = check_llama()
    qdrant = check_qdrant()
    memories = {
        "engineering": memory_stats(ENGINEERING_MEMORY_DIR),
        "code": memory_stats(CODE_MEMORY_DIR),
    }
    logs = {
        "memory": log_stats(MEMORY_LOG),
        "code": log_stats(CODE_LOG),
    }
    system = system_stats()

    subsystem_checks = [
        llama,
        qdrant,
        memories["engineering"],
        memories["code"],
        logs["memory"],
        logs["code"],
        system,
    ]

    return {
        "ok": all(check.get("ok") for check in subsystem_checks),
        "timestamp": iso_time(time.time()),
        "llama": llama,
        "qdrant": qdrant,
        "memories": memories,
        "system": system,
        "logs": logs,
    }
