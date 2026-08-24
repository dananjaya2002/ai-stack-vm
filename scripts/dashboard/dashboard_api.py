import os
import re
import hmac
import hashlib
import secrets
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
import zipfile
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import psutil
import requests
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ai_stack_rag.utils.log_status import log_stats as classify_log_stats, read_last_lines as read_log_lines

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIST_DIR = BASE_DIR / "frontend" / "dist"

load_dotenv()

LLAMA_BASE_URL = os.getenv("LLAMA_BASE_URL", "http://localhost:8082/v1").rstrip("/")
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333").rstrip("/")
QDRANT_HOST = os.getenv("QDRANT_HOST", "qdrant")
QDRANT_PORT = os.getenv("QDRANT_PORT", "6333")

ENGINEERING_MEMORY_DIR = Path(os.getenv("ENGINEERING_MEMORY_DIR", "/memory/engineering-memory"))
CODE_MEMORY_DIR = Path(os.getenv("CODE_MEMORY_DIR", "/memory/code-memory"))
MEMORY_LOG = Path(os.getenv("MEMORY_LOG", "/logs/memory/memory_api.log"))
CODE_LOG = Path(os.getenv("CODE_LOG", "/logs/code/code_proxy.log"))
AGENTIC_RAG_LOG = Path(os.getenv("AGENTIC_RAG_LOG", "/logs/agentic-rag/agentic_rag.log"))
MEMORY_LOG_ENABLED = os.getenv("MEMORY_LOG_ENABLED", "true").lower() == "true"
CODE_LOG_ENABLED = os.getenv("CODE_LOG_ENABLED", "true").lower() == "true"
AGENTIC_RAG_LOG_ENABLED = os.getenv("AGENTIC_RAG_LOG_ENABLED", "true").lower() == "true"
DASHBOARD_LOG_DIR = Path(os.getenv("DASHBOARD_LOG_DIR", "/tmp/ai-stack-dashboard"))
AI_STACK_ENV_FILE = Path(os.getenv("AI_STACK_ENV_FILE", "/config/ai-stack.env"))

CONFIG_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "SKIP_UTILITY_PROMPTS": {"group": "General", "type": "boolean", "default": "true"},
    "ENABLE_RATE_LIMIT": {"group": "General", "type": "boolean", "default": "true"},
    "RATE_LIMIT_PER_MINUTE": {"group": "General", "type": "integer", "default": "60", "min": 1, "max": 10000},
    "LLAMA_CONTEXT": {"group": "Model", "type": "integer", "default": "8192", "min": 512, "max": 131072},
    "LLAMA_THREADS": {"group": "Model", "type": "integer", "default": "6", "min": 1, "max": 256},
    "LLAMA_BATCH": {"group": "Model", "type": "integer", "default": "512", "min": 1, "max": 8192},
    "LLAMA_UBATCH": {"group": "Model", "type": "integer", "default": "256", "min": 1, "max": 8192},
    "MEMORY_API_LOGS": {"group": "Document Memory", "type": "boolean", "default": "true"},
    "MEMORY_TOP_K": {"group": "Document Memory", "type": "integer", "default": "5", "min": 1, "max": 50},
    "MEMORY_SCORE_THRESHOLD": {"group": "Document Memory", "type": "number", "default": "0.25", "min": 0, "max": 1},
    "CODE_PROXY_LOGS": {"group": "Code Memory", "type": "boolean", "default": "true"},
    "CODE_TOP_K": {"group": "Code Memory", "type": "integer", "default": "8", "min": 1, "max": 50},
    "CODE_SCORE_THRESHOLD": {"group": "Code Memory", "type": "number", "default": "0.25", "min": 0, "max": 1},
    "MAX_CHUNKS_PER_FILE": {"group": "Code Memory", "type": "integer", "default": "2", "min": 1, "max": 20},
    "SEARCH_LIMIT_MULTIPLIER": {"group": "Code Memory", "type": "integer", "default": "4", "min": 1, "max": 20},
    "AGENTIC_RAG_LOGS": {"group": "Agentic RAG", "type": "boolean", "default": "true"},
    "ENABLE_INDEX_V2": {"group": "Agentic RAG", "type": "boolean", "default": "true"},
    "ENABLE_AGENTIC_RETRIEVAL": {"group": "Agentic RAG", "type": "boolean", "default": "true"},
    "AGENTIC_MAX_STEPS": {"group": "Agentic RAG", "type": "integer", "default": "4", "min": 1, "max": 12},
    "AGENTIC_INITIAL_SUBQUERIES": {"group": "Agentic RAG", "type": "integer", "default": "3", "min": 1, "max": 12},
    "AGENTIC_FOLLOWUP_TOP_K": {"group": "Agentic RAG", "type": "integer", "default": "4", "min": 1, "max": 50},
    "AGENTIC_MAX_TOTAL_CHUNKS": {"group": "Agentic RAG", "type": "integer", "default": "16", "min": 1, "max": 100},
    "AGENTIC_MIN_CONFIDENCE": {"group": "Agentic RAG", "type": "number", "default": "0.70", "min": 0, "max": 1},
    "AGENTIC_TOP_K_PER_QUERY": {"group": "Agentic RAG", "type": "integer", "default": "3", "min": 1, "max": 50},
    "SIMPLE_TOP_K": {"group": "Agentic RAG", "type": "integer", "default": "6", "min": 1, "max": 50},
    "AGENTIC_SCORE_THRESHOLD": {"group": "Agentic RAG", "type": "number", "default": "0.20", "min": 0, "max": 1},
    "MAX_CHUNK_CHARS": {"group": "Agentic RAG", "type": "integer", "default": "4000", "min": 100, "max": 50000},
    "MAX_CONTEXT_CHARS": {"group": "Agentic RAG", "type": "integer", "default": "50000", "min": 1000, "max": 500000},
}

CONFIG_PRESENTATION: Dict[str, Dict[str, str]] = {
    "SKIP_UTILITY_PROMPTS": {"label": "Skip retrieval for utility prompts", "description": "Send Open WebUI title, tag, and follow-up requests directly to the model without RAG retrieval."},
    "ENABLE_RATE_LIMIT": {"label": "Enable rate limiting", "description": "Limit how frequently clients can call the proxy APIs."},
    "RATE_LIMIT_PER_MINUTE": {"label": "Requests per minute", "description": "Maximum requests accepted from a client during one minute."},
    "LLAMA_CONTEXT": {"label": "Model context window", "description": "Maximum tokens the model can consider in one request. Larger values use more memory."},
    "LLAMA_THREADS": {"label": "Model CPU threads", "description": "CPU threads used by llama.cpp for inference."},
    "LLAMA_BATCH": {"label": "Prompt batch size", "description": "Number of prompt tokens processed together. Larger batches can improve speed but use more memory."},
    "LLAMA_UBATCH": {"label": "Physical batch size", "description": "Maximum tokens processed in one physical llama.cpp batch."},
    "MEMORY_API_LOGS": {"label": "Document logging", "description": "Write document-memory retrieval events to the persistent log file."},
    "MEMORY_TOP_K": {"label": "Document results", "description": "Maximum document chunks supplied to the model for an answer."},
    "MEMORY_SCORE_THRESHOLD": {"label": "Document relevance threshold", "description": "Minimum similarity score for accepting a document chunk. Lower values return more results."},
    "CODE_PROXY_LOGS": {"label": "Code logging", "description": "Write code retrieval events to the persistent log file."},
    "CODE_TOP_K": {"label": "Code results", "description": "Maximum code chunks supplied to the model for an answer."},
    "CODE_SCORE_THRESHOLD": {"label": "Code relevance threshold", "description": "Minimum similarity score for accepting a code chunk."},
    "MAX_CHUNKS_PER_FILE": {"label": "Chunks per file", "description": "Maximum chunks selected from one code file to keep results diverse."},
    "SEARCH_LIMIT_MULTIPLIER": {"label": "Search candidate multiplier", "description": "Extra Qdrant candidates fetched before local filtering and ranking."},
    "AGENTIC_RAG_LOGS": {"label": "Agentic RAG logging", "description": "Write retrieval steps, confidence, timing, and stop reasons to the Agentic RAG log."},
    "ENABLE_INDEX_V2": {"label": "Use enhanced index", "description": "Enable metadata-aware chunks and retrieval behavior from the enhanced index."},
    "ENABLE_AGENTIC_RETRIEVAL": {"label": "Enable agentic retrieval", "description": "Allow multi-step planning, evidence evaluation, and follow-up searches."},
    "AGENTIC_MAX_STEPS": {"label": "Maximum retrieval steps", "description": "Safety limit for iterative Agentic RAG searches."},
    "AGENTIC_INITIAL_SUBQUERIES": {"label": "Initial subqueries", "description": "Maximum focused searches created during the first retrieval step."},
    "AGENTIC_FOLLOWUP_TOP_K": {"label": "Follow-up results", "description": "Maximum results fetched for each follow-up evidence query."},
    "AGENTIC_MAX_TOTAL_CHUNKS": {"label": "Total evidence limit", "description": "Maximum unique chunks retained across every retrieval step."},
    "AGENTIC_MIN_CONFIDENCE": {"label": "Required confidence", "description": "Confidence needed before Agentic RAG considers the evidence sufficient."},
    "AGENTIC_TOP_K_PER_QUERY": {"label": "Initial results per query", "description": "Maximum chunks fetched for each initial retrieval query."},
    "SIMPLE_TOP_K": {"label": "Simple retrieval results", "description": "Maximum chunks used when multi-step agentic retrieval is disabled."},
    "AGENTIC_SCORE_THRESHOLD": {"label": "Agentic relevance threshold", "description": "Minimum Qdrant similarity score accepted by Agentic RAG."},
    "MAX_CHUNK_CHARS": {"label": "Maximum chunk length", "description": "Maximum characters retained from an individual evidence chunk."},
    "MAX_CONTEXT_CHARS": {"label": "Maximum evidence context", "description": "Maximum combined evidence characters passed to the answer model."},
}

INDEX_MEMORY_MODULE = os.getenv("INDEX_MEMORY_MODULE", "ai_stack_rag.ingestion.memory")
INDEX_CODE_MODULE = os.getenv("INDEX_CODE_MODULE", "ai_stack_rag.ingestion.code")
WATCH_MEMORY_MODULE = os.getenv("WATCH_MEMORY_MODULE", "ai_stack_rag.ingestion.watch_memory")
WATCH_CODE_MODULE = os.getenv("WATCH_CODE_MODULE", "ai_stack_rag.ingestion.watch_code")
PYTHON_BIN = os.getenv("PYTHON_BIN", "python")

HTTP_TIMEOUT_SECONDS = float(os.getenv("DASHBOARD_HTTP_TIMEOUT_SECONDS", "3"))
MAX_LOG_LINES = int(os.getenv("DASHBOARD_MAX_LOG_LINES", "400"))
MAX_UPLOAD_BYTES = int(os.getenv("DASHBOARD_MAX_UPLOAD_BYTES", str(100 * 1024 * 1024)))
ENGINEERING_UPLOAD_SUFFIXES = frozenset({".md"})
CODE_UPLOAD_SUFFIXES = frozenset({
    ".zip", ".txt", ".py", ".js", ".jsx", ".ts", ".tsx", ".dart", ".java",
    ".go", ".rs", ".c", ".h", ".cpp", ".hpp", ".cs", ".php", ".rb", ".sh",
    ".bash", ".zsh", ".yaml", ".yml", ".json", ".md", ".html", ".css", ".scss",
    ".sql", ".xml", ".toml", ".ini",
})
SECURITY_MODE = os.getenv("SECURITY_MODE", "development").strip().lower()
DASHBOARD_AUTH_MODE = os.getenv("DASHBOARD_AUTH_MODE", "auto").strip().lower()
DASHBOARD_ADMIN_USERNAME = os.getenv("DASHBOARD_ADMIN_USERNAME", "admin")
DASHBOARD_ADMIN_PASSWORD_HASH = os.getenv("DASHBOARD_ADMIN_PASSWORD_HASH", "").strip()
DASHBOARD_SESSION_SECRET = os.getenv("DASHBOARD_SESSION_SECRET", "").strip()
DASHBOARD_SESSION_COOKIE = os.getenv("DASHBOARD_SESSION_COOKIE", "ai_stack_dashboard_session")
DASHBOARD_COOKIE_SECURE = os.getenv("DASHBOARD_COOKIE_SECURE", "false").strip().lower() in {"1", "true", "yes", "on"}
DASHBOARD_SESSION_TTL_SECONDS = int(os.getenv("DASHBOARD_SESSION_TTL_SECONDS", str(12 * 60 * 60)))

app = FastAPI(title="AI Stack Dashboard")

if (FRONTEND_DIST_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST_DIR / "assets"), name="assets")

JOBS: Dict[str, Dict[str, Any]] = {}
JOBS_LOCK = threading.Lock()
WATCHERS: Dict[str, Dict[str, Any]] = {}
WATCHERS_LOCK = threading.Lock()
LOG_CAPTURE = {"enabled": True}


class CloneRequest(BaseModel):
    repo_url: str
    repo_name: Optional[str] = None
    token: Optional[str] = None
    update_existing: bool = False


class IndexRequest(BaseModel):
    scope: str
    target: Optional[str] = None


class LogCaptureRequest(BaseModel):
    enabled: bool


class LogResetRequest(BaseModel):
    source: str


class ConfigUpdateRequest(BaseModel):
    values: Dict[str, str]


class DeleteFileRequest(BaseModel):
    scope: str
    path: str


class QdrantResetRequest(BaseModel):
    target: str
    confirmation: str


class LoginRequest(BaseModel):
    username: str
    password: str


def dashboard_auth_required() -> bool:
    if DASHBOARD_AUTH_MODE == "disabled":
        return False
    if DASHBOARD_AUTH_MODE == "required":
        return True
    if DASHBOARD_AUTH_MODE != "auto":
        return SECURITY_MODE == "production"
    return SECURITY_MODE == "production"


def dashboard_auth_configured() -> bool:
    return bool(DASHBOARD_ADMIN_PASSWORD_HASH and DASHBOARD_SESSION_SECRET)


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def password_matches(password: str) -> bool:
    expected = DASHBOARD_ADMIN_PASSWORD_HASH.removeprefix("sha256:").lower()
    return hmac.compare_digest(hash_password(password), expected)


def sign_session(username: str, issued_at: int) -> str:
    payload = f"{username}:{issued_at}"
    signature = hmac.new(DASHBOARD_SESSION_SECRET.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}:{signature}"


def valid_session(raw_session: str) -> bool:
    if not raw_session or not DASHBOARD_SESSION_SECRET:
        return False
    parts = raw_session.split(":")
    if len(parts) != 3:
        return False
    username, issued_at_raw, signature = parts
    if username != DASHBOARD_ADMIN_USERNAME:
        return False
    try:
        issued_at = int(issued_at_raw)
    except ValueError:
        return False
    if time.time() - issued_at > DASHBOARD_SESSION_TTL_SECONDS:
        return False
    expected = sign_session(username, issued_at).rsplit(":", 1)[1]
    return hmac.compare_digest(signature, expected)


def set_session_cookie(response: Response) -> None:
    response.set_cookie(
        DASHBOARD_SESSION_COOKIE,
        sign_session(DASHBOARD_ADMIN_USERNAME, int(time.time())),
        max_age=DASHBOARD_SESSION_TTL_SECONDS,
        httponly=True,
        secure=DASHBOARD_COOKIE_SECURE,
        samesite="strict",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(DASHBOARD_SESSION_COOKIE, httponly=True, secure=DASHBOARD_COOKIE_SECURE, samesite="strict")


def auth_status_payload(request: Request) -> Dict[str, Any]:
    required = dashboard_auth_required()
    configured = dashboard_auth_configured()
    authenticated = not required or valid_session(request.cookies.get(DASHBOARD_SESSION_COOKIE, ""))
    return {
        "required": required,
        "configured": configured,
        "authenticated": authenticated,
        "username": DASHBOARD_ADMIN_USERNAME if authenticated and required else None,
        "mode": DASHBOARD_AUTH_MODE,
    }


@app.middleware("http")
async def dashboard_auth_middleware(request: Request, call_next):
    path = request.url.path
    if not dashboard_auth_required():
        return await call_next(request)
    if path == "/" or path.startswith("/assets/") or path.startswith("/api/dashboard/auth/"):
        return await call_next(request)
    if not path.startswith("/api/dashboard"):
        return await call_next(request)
    if not dashboard_auth_configured():
        return JSONResponse(status_code=503, content={"error": "Dashboard authentication is not configured."})
    if not valid_session(request.cookies.get(DASHBOARD_SESSION_COOKIE, "")):
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})
    return await call_next(request)


def iso_time(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def now_iso() -> str:
    return iso_time(time.time())


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
            f"Cannot reach llama service at {LLAMA_BASE_URL}/models. "
            "Inside compose this should usually be http://vm-llama:8082/v1. "
            f"Details: {exc}",
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
        result["chat_latency_ms"] = latency_ms
        result["approximate_token_speed"] = extract_token_speed(response.json(), latency_ms)
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
    return error_payload(
        "Cannot reach Qdrant. Inside compose this should usually be http://qdrant:6333. "
        f"Checked {QDRANT_URL}. Details: {'; '.join(errors)}",
        url=QDRANT_URL,
        latency_ms=None,
    )


def non_secret_settings() -> Dict[str, Any]:
    names = [
        "SECURITY_MODE",
        "DASHBOARD_AUTH_MODE",
        "DASHBOARD_ADMIN_USERNAME",
        "BIND_HOST",
        "OPEN_WEBUI_BIND_HOST",
        "DASHBOARD_BIND_HOST",
        "LLAMA_BASE_URL",
        "QDRANT_URL",
        "QDRANT_HOST",
        "QDRANT_PORT",
        "MEMORY_COLLECTION",
        "CODE_COLLECTION",
        "MODEL_NAME",
        "MODEL_FILE",
        "MODEL_PROFILE",
        "MEMORY_TOP_K",
        "CODE_TOP_K",
        "AGENTIC_MAX_STEPS",
        "AGENTIC_MIN_CONFIDENCE",
    ]
    return {name: os.getenv(name, "") for name in names}


def read_env_values() -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not AI_STACK_ENV_FILE.exists():
        return values
    for raw_line in AI_STACK_ENV_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        values[name.strip()] = value.strip()
    return values


def validate_config_value(name: str, raw_value: str) -> str:
    definition = CONFIG_DEFINITIONS.get(name)
    if not definition:
        raise HTTPException(status_code=400, detail=f"Unsupported configuration variable: {name}")
    value = str(raw_value).strip()
    value_type = definition["type"]
    if value_type == "boolean":
        normalized = value.lower()
        if normalized not in {"true", "false"}:
            raise HTTPException(status_code=400, detail=f"{name} must be true or false.")
        return normalized
    try:
        parsed = int(value) if value_type == "integer" else float(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{name} must be a valid {value_type}.") from exc
    if parsed < definition["min"] or parsed > definition["max"]:
        raise HTTPException(
            status_code=400,
            detail=f"{name} must be between {definition['min']} and {definition['max']}.",
        )
    return str(parsed)


def write_env_values(updates: Dict[str, str]) -> None:
    if not AI_STACK_ENV_FILE.exists() or not AI_STACK_ENV_FILE.is_file():
        raise HTTPException(status_code=503, detail="The host .env file is not mounted into the dashboard.")
    normalized = {name: validate_config_value(name, value) for name, value in updates.items()}
    lines = AI_STACK_ENV_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
    found = set()
    output = []
    for line in lines:
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=", line)
        name = match.group(1) if match else None
        if name in normalized:
            output.append(f"{name}={normalized[name]}")
            found.add(name)
        else:
            output.append(line)
    if normalized.keys() - found:
        output.extend(["", "# Dashboard-managed configuration"])
        output.extend(f"{name}={normalized[name]}" for name in normalized if name not in found)
    AI_STACK_ENV_FILE.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")


def editable_config_payload() -> Dict[str, Any]:
    env_values = read_env_values()
    values = {
        name: env_values.get(name, os.getenv(name, definition["default"]))
        for name, definition in CONFIG_DEFINITIONS.items()
    }
    return {
        "values": values,
        "definitions": {
            name: {**definition, **CONFIG_PRESENTATION[name]}
            for name, definition in CONFIG_DEFINITIONS.items()
        },
        "env_file_available": AI_STACK_ENV_FILE.is_file(),
        "restart_required": True,
    }


def qdrant_request(method: str, path: str, body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    response = requests.request(method, f"{QDRANT_URL}{path}", json=body, timeout=max(HTTP_TIMEOUT_SECONDS, 10))
    response.raise_for_status()
    try:
        parsed: Any = response.json()
    except ValueError:
        parsed = response.text
    return {"ok": True, "body": parsed, "status_code": response.status_code}


def qdrant_collections_payload() -> Dict[str, Any]:
    data = qdrant_request("GET", "/collections")["body"]
    collections = []
    raw_collections = data.get("result", {}).get("collections", []) if isinstance(data, dict) else []
    for item in raw_collections:
        name = item.get("name")
        if not name:
            continue
        detail: Dict[str, Any] = {"name": name}
        try:
            detail_body = qdrant_request("GET", f"/collections/{name}")["body"]
            result = detail_body.get("result", {}) if isinstance(detail_body, dict) else {}
            detail["points_count"] = result.get("points_count")
            detail["vectors_count"] = result.get("vectors_count")
            detail["status"] = result.get("status")
        except Exception as exc:
            detail["error"] = str(exc)
        collections.append(detail)
    return {"ok": True, "collections": collections}


def delete_qdrant_collection(collection: str) -> None:
    qdrant_request("DELETE", f"/collections/{collection}")


def delete_demo_vectors() -> List[str]:
    memory_collection = os.getenv("MEMORY_COLLECTION", "engineering-memory")
    code_collection = os.getenv("CODE_COLLECTION", "code-memory")
    warnings = []
    try:
        qdrant_request(
            "POST",
            f"/collections/{memory_collection}/points/delete",
            {"filter": {"must": [{"key": "category", "match": {"value": "demo"}}]}},
        )
    except Exception as exc:
        warnings.append(f"memory demo vector cleanup skipped: {exc}")
    try:
        qdrant_request(
            "POST",
            f"/collections/{code_collection}/points/delete",
            {
                "filter": {
                    "should": [
                        {"key": "repo", "match": {"value": "sample-python-app"}},
                        {"key": "repo", "match": {"value": "sample-repository-app"}},
                    ]
                }
            },
        )
    except Exception as exc:
        warnings.append(f"code demo vector cleanup skipped: {exc}")
    return warnings


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


def log_stats(path: Path, enabled: bool = True) -> Dict[str, Any]:
    return classify_log_stats(path, enabled)


def system_stats() -> Dict[str, Any]:
    try:
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        return {
            "ok": True,
            "error": None,
            "cpu": {"usage_percent": psutil.cpu_percent(interval=0.1), "count": psutil.cpu_count()},
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


def scope_root(scope: str) -> Path:
    if scope == "engineering":
        return ENGINEERING_MEMORY_DIR
    if scope == "code":
        return CODE_MEMORY_DIR
    raise HTTPException(status_code=400, detail="scope must be engineering or code")


def safe_relative_path(raw_path: str) -> Path:
    cleaned = (raw_path or "").replace("\\", "/").strip("/")
    path = Path(cleaned)
    if not cleaned or path.is_absolute() or ".." in path.parts:
        raise HTTPException(status_code=400, detail="Invalid path.")
    return path


def safe_join(root: Path, raw_path: Optional[str]) -> Path:
    root = root.resolve()
    if not raw_path:
        return root
    candidate = (root / safe_relative_path(raw_path)).resolve()
    if candidate != root and root not in candidate.parents:
        raise HTTPException(status_code=400, detail="Path escapes memory directory.")
    return candidate


def list_files(scope: str) -> Dict[str, Any]:
    root = scope_root(scope)
    if not root.exists():
        return {"ok": False, "error": "Directory does not exist.", "scope": scope, "root": str(root), "files": []}

    files = []
    for item in sorted(root.rglob("*")):
        if not item.is_file():
            continue
        try:
            stat = item.stat()
            relative_path = str(item.relative_to(root))
        except Exception:
            continue
        files.append(
            {
                "scope": scope,
                "path": relative_path,
                "size_bytes": stat.st_size,
                "modified_time": iso_time(stat.st_mtime),
                "extension": item.suffix.lower(),
            }
        )

    return {"ok": True, "error": None, "scope": scope, "root": str(root), "files": files}


def directory_child_count(path: Path) -> int:
    try:
        return sum(1 for _ in path.iterdir())
    except Exception:
        return 0


def list_directory(scope: str, raw_path: Optional[str]) -> Dict[str, Any]:
    root = scope_root(scope)
    current = safe_join(root, raw_path)

    if not root.exists():
        return {
            "ok": False,
            "error": "Directory does not exist.",
            "scope": scope,
            "root": str(root),
            "path": "",
            "entries": [],
            "files": [],
        }
    if not current.exists():
        raise HTTPException(status_code=404, detail="Directory does not exist.")
    if not current.is_dir():
        raise HTTPException(status_code=400, detail="Path is not a directory.")

    entries = []
    for item in sorted(current.iterdir(), key=lambda entry: (not entry.is_dir(), entry.name.lower())):
        try:
            stat = item.stat()
            relative_path = str(item.relative_to(root))
        except Exception:
            continue

        is_dir = item.is_dir()
        entries.append(
            {
                "scope": scope,
                "name": item.name,
                "path": relative_path,
                "kind": "directory" if is_dir else "file",
                "size_bytes": None if is_dir else stat.st_size,
                "modified_time": iso_time(stat.st_mtime),
                "extension": "" if is_dir else item.suffix.lower(),
                "child_count": directory_child_count(item) if is_dir else None,
                "can_delete": True,
            }
        )

    files = [entry for entry in entries if entry["kind"] == "file"]
    relative_current = "" if current == root.resolve() else str(current.relative_to(root.resolve()))
    return {
        "ok": True,
        "error": None,
        "scope": scope,
        "root": str(root),
        "path": relative_current,
        "entries": entries,
        "files": files,
    }


def read_last_lines(
    path: Path, source: str, enabled: bool = True, max_lines: int = MAX_LOG_LINES
) -> Dict[str, Any]:
    return read_log_lines(path, source, enabled, max_lines)


def redact(text: str, secrets: Optional[List[str]] = None) -> str:
    redacted = text
    for secret in secrets or []:
        if secret:
            redacted = redacted.replace(secret, "[redacted]")
    redacted = re.sub(r"https://[^@\s]+@", "https://[redacted]@", redacted)
    return redacted


def append_job_output(job: Dict[str, Any], line: str, secrets: Optional[List[str]] = None) -> None:
    if not LOG_CAPTURE["enabled"]:
        return
    clean = redact(line.rstrip(), secrets)
    output = job.setdefault("output", [])
    output.append(clean)
    del output[:-MAX_LOG_LINES]


def job_public(job: Dict[str, Any]) -> Dict[str, Any]:
    public = dict(job)
    public["output"] = list(job.get("output", []))[-MAX_LOG_LINES:]
    return public


def record_dashboard_event(name: str, lines: List[str]) -> None:
    if not LOG_CAPTURE["enabled"]:
        return
    job_id = str(uuid.uuid4())
    with JOBS_LOCK:
        JOBS[job_id] = {
            "id": job_id,
            "name": name,
            "status": "succeeded",
            "command": [],
            "started_at": now_iso(),
            "finished_at": now_iso(),
            "duration_seconds": 0,
            "exit_code": 0,
            "output": lines[-MAX_LOG_LINES:],
        }


def run_job(name: str, command: List[str], env: Optional[Dict[str, str]] = None, cwd: Optional[Path] = None, secrets: Optional[List[str]] = None) -> Dict[str, Any]:
    job_id = str(uuid.uuid4())
    job = {
        "id": job_id,
        "name": name,
        "status": "running",
        "command": [redact(part, secrets) for part in command],
        "started_at": now_iso(),
        "finished_at": None,
        "duration_seconds": None,
        "exit_code": None,
        "output": [],
    }

    with JOBS_LOCK:
        for existing in JOBS.values():
            if existing.get("status") == "running" and existing.get("name") == name:
                raise HTTPException(status_code=409, detail=f"Job already running: {name}")
        JOBS[job_id] = job

    def worker() -> None:
        started = time.time()
        try:
            process = subprocess.Popen(
                command,
                cwd=str(cwd) if cwd else None,
                env=env or os.environ.copy(),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            job["pid"] = process.pid
            assert process.stdout is not None
            for line in process.stdout:
                append_job_output(job, line, secrets)
            exit_code = process.wait()
            job["exit_code"] = exit_code
            job["status"] = "succeeded" if exit_code == 0 else "failed"
        except Exception as exc:
            job["status"] = "failed"
            job["error"] = redact(str(exc), secrets)
        finally:
            job["finished_at"] = now_iso()
            job["duration_seconds"] = round(time.time() - started, 2)

    threading.Thread(target=worker, daemon=True).start()
    return job_public(job)


def index_env(collection: str, root: Path) -> Dict[str, str]:
    env = os.environ.copy()
    env["QDRANT_HOST"] = QDRANT_HOST
    env["QDRANT_PORT"] = QDRANT_PORT
    env["QDRANT_COLLECTION"] = collection
    env["MEMORY_DIR"] = str(root)
    env["MEMORY_ROOT"] = str(root)
    env["REPOS_ROOT"] = str(CODE_MEMORY_DIR)
    return env


def infer_repo_name(repo_url: str) -> str:
    path = urlparse(repo_url).path.rstrip("/")
    name = Path(path).name
    if name.endswith(".git"):
        name = name[:-4]
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip(".-")
    if not name:
        raise HTTPException(status_code=400, detail="Could not infer repository name.")
    return name


def build_git_env(token: Optional[str]) -> Dict[str, str]:
    env = os.environ.copy()
    if not token:
        return env

    askpass_dir = Path(tempfile.mkdtemp(prefix="dashboard-git-askpass-"))
    askpass_script = askpass_dir / "askpass.sh"
    askpass_script.write_text(
        "#!/bin/sh\n"
        "case \"$1\" in\n"
        "*Username*) printf '%s\\n' x-access-token ;;\n"
        "*) printf '%s\\n' \"$DASHBOARD_GIT_TOKEN\" ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    askpass_script.chmod(0o700)
    env["GIT_ASKPASS"] = str(askpass_script)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["DASHBOARD_GIT_TOKEN"] = token
    return env


def save_upload(upload: UploadFile, destination_root: Path) -> Dict[str, Any]:
    relative_path = safe_relative_path(upload.filename or "")
    destination = safe_join(destination_root, str(relative_path))
    destination.parent.mkdir(parents=True, exist_ok=True)

    total = 0
    with destination.open("wb") as handle:
        while True:
            chunk = upload.file.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_UPLOAD_BYTES:
                raise HTTPException(status_code=413, detail=f"Upload exceeds {MAX_UPLOAD_BYTES} bytes.")
            handle.write(chunk)

    return {"filename": upload.filename, "path": str(destination.relative_to(destination_root)), "size_bytes": total}


def validate_upload_extension(scope: str, filename: str) -> None:
    allowed = ENGINEERING_UPLOAD_SUFFIXES if scope == "engineering" else CODE_UPLOAD_SUFFIXES
    suffix = Path(filename).suffix.lower()
    if suffix not in allowed:
        supported = ", ".join(sorted(allowed))
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported {scope} upload type '{suffix or '[no extension]'}'. Supported: {supported}",
        )


def extract_zip_safe(zip_path: Path, destination_root: Path) -> List[str]:
    extracted = []
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            target = safe_join(destination_root, member.filename)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, target.open("wb") as destination:
                shutil.copyfileobj(source, destination)
            extracted.append(str(target.relative_to(destination_root)))
    zip_path.unlink(missing_ok=True)
    return extracted


def delete_memory_file(scope: str, relative_path: str) -> Dict[str, Any]:
    root = scope_root(scope)
    target = safe_join(root, relative_path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="Path does not exist.")

    if target.is_dir():
        file_count = sum(1 for item in target.rglob("*") if item.is_file())
        shutil.rmtree(target)
        deleted_kind = "directory"
        size_bytes = 0
    elif target.is_file():
        size_bytes = target.stat().st_size
        target.unlink()
        deleted_kind = "file"
        file_count = 1
    else:
        raise HTTPException(status_code=400, detail="Only files and directories can be deleted.")

    record_dashboard_event(
        f"delete {scope}",
        [
            f"Deleted {deleted_kind} {relative_path} from {scope} memory.",
            f"Files removed: {file_count}",
        ],
    )
    return {"ok": True, "scope": scope, "path": relative_path, "kind": deleted_kind, "size_bytes": size_bytes, "file_count": file_count}


def watcher_public(scope: str, watcher: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not watcher:
        return {"scope": scope, "running": False}
    process = watcher.get("process")
    running = bool(process and process.poll() is None)
    return {
        "scope": scope,
        "running": running,
        "pid": process.pid if running else watcher.get("pid"),
        "started_at": watcher.get("started_at"),
        "uptime_seconds": round(time.time() - watcher["started_ts"], 2) if running else None,
        "watched_path": watcher.get("watched_path"),
        "output": list(watcher.get("output", []))[-MAX_LOG_LINES:],
    }


def dashboard_index_path() -> Path:
    vite_index = FRONTEND_DIST_DIR / "index.html"
    if vite_index.exists():
        return vite_index
    raise HTTPException(
        status_code=503,
        detail="Dashboard frontend build is missing. Run npm run build in scripts/dashboard/frontend or rebuild the dashboard image.",
    )


@app.get("/")
def dashboard_home() -> FileResponse:
    return FileResponse(dashboard_index_path())


@app.get("/api/dashboard/auth/status")
def dashboard_auth_status(request: Request) -> Dict[str, Any]:
    return auth_status_payload(request)


@app.post("/api/dashboard/auth/login")
def dashboard_login(req: LoginRequest, request: Request, response: Response) -> Dict[str, Any]:
    if not dashboard_auth_required():
        return auth_status_payload(request)
    if not dashboard_auth_configured():
        raise HTTPException(status_code=503, detail="Dashboard authentication is not configured.")
    if req.username != DASHBOARD_ADMIN_USERNAME or not password_matches(req.password):
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    set_session_cookie(response)
    return {
        "required": True,
        "configured": True,
        "authenticated": True,
        "username": DASHBOARD_ADMIN_USERNAME,
        "mode": DASHBOARD_AUTH_MODE,
    }


@app.post("/api/dashboard/auth/logout")
def dashboard_logout(request: Request, response: Response) -> Dict[str, Any]:
    clear_session_cookie(response)
    return auth_status_payload(request) | {"authenticated": False}


@app.get("/api/dashboard/status")
def dashboard_status() -> Dict[str, Any]:
    llama = check_llama()
    qdrant = check_qdrant()
    memories = {"engineering": memory_stats(ENGINEERING_MEMORY_DIR), "code": memory_stats(CODE_MEMORY_DIR)}
    logs = {
        "memory": log_stats(MEMORY_LOG, MEMORY_LOG_ENABLED),
        "code": log_stats(CODE_LOG, CODE_LOG_ENABLED),
        "agentic-rag": log_stats(AGENTIC_RAG_LOG, AGENTIC_RAG_LOG_ENABLED),
    }
    system = system_stats()
    strict_checks = [llama, qdrant, memories["engineering"], memories["code"], system]

    return {
        "ok": all(check.get("ok") for check in strict_checks),
        "timestamp": now_iso(),
        "llama": llama,
        "qdrant": qdrant,
        "memories": memories,
        "system": system,
        "logs": logs,
        "log_capture": LOG_CAPTURE,
        "watchers": list_watchers(),
    }


@app.get("/api/dashboard/settings")
def dashboard_settings() -> Dict[str, Any]:
    return {
        "ok": True,
        "settings": non_secret_settings(),
        "configuration": editable_config_payload(),
        "paths": {
            "document_memory": str(ENGINEERING_MEMORY_DIR),
            "code_memory": str(CODE_MEMORY_DIR),
            "memory_log": str(MEMORY_LOG),
            "code_log": str(CODE_LOG),
            "agentic_rag_log": str(AGENTIC_RAG_LOG),
            "dashboard_log_dir": str(DASHBOARD_LOG_DIR),
        },
    }


@app.put("/api/dashboard/config")
def update_dashboard_config(req: ConfigUpdateRequest) -> Dict[str, Any]:
    write_env_values(req.values)
    return {"ok": True, "configuration": editable_config_payload(), "restart_required": True}


@app.post("/api/dashboard/config/reset")
def reset_dashboard_config() -> Dict[str, Any]:
    write_env_values({name: definition["default"] for name, definition in CONFIG_DEFINITIONS.items()})
    return {"ok": True, "configuration": editable_config_payload(), "restart_required": True}


@app.get("/api/dashboard/qdrant/collections")
def dashboard_qdrant_collections() -> Dict[str, Any]:
    try:
        return qdrant_collections_payload()
    except Exception as exc:
        return error_payload(str(exc), collections=[])


@app.post("/api/dashboard/qdrant/reset")
def dashboard_qdrant_reset(req: QdrantResetRequest) -> Dict[str, Any]:
    expected = f"reset {req.target}"
    if req.confirmation != expected:
        raise HTTPException(status_code=400, detail=f"Type '{expected}' to confirm.")

    warnings: List[str] = []
    if req.target == "memory":
        collection = os.getenv("MEMORY_COLLECTION", "engineering-memory")
        delete_qdrant_collection(collection)
    elif req.target == "code":
        collection = os.getenv("CODE_COLLECTION", "code-memory")
        delete_qdrant_collection(collection)
    elif req.target == "demo":
        warnings = delete_demo_vectors()
    else:
        raise HTTPException(status_code=400, detail="target must be memory, code, or demo")

    return {"ok": True, "target": req.target, "warnings": warnings}


@app.get("/api/dashboard/files")
def dashboard_files(scope: str, path: Optional[str] = None, flat: bool = False) -> Dict[str, Any]:
    if flat:
        return list_files(scope)
    return list_directory(scope, path)


@app.delete("/api/dashboard/files")
def dashboard_delete_file(req: DeleteFileRequest) -> Dict[str, Any]:
    return delete_memory_file(req.scope, req.path)


@app.get("/api/dashboard/logs")
def dashboard_logs(source: str = "dashboard") -> Dict[str, Any]:
    if source == "memory":
        return read_last_lines(MEMORY_LOG, source, MEMORY_LOG_ENABLED)
    if source == "code":
        return read_last_lines(CODE_LOG, source, CODE_LOG_ENABLED)
    if source == "agentic-rag":
        return read_last_lines(AGENTIC_RAG_LOG, source, AGENTIC_RAG_LOG_ENABLED)
    if source == "dashboard":
        with JOBS_LOCK:
            lines = []
            for job in JOBS.values():
                lines.append(f"[{job['status']}] {job['name']} {job['id']}")
                lines.extend(job.get("output", [])[-80:])
            return {
                "ok": True, "error": None, "source": source,
                "state": "available" if lines else "empty", "enabled": LOG_CAPTURE["enabled"],
                "message": None if lines else (
                    "No dashboard activity has been captured yet."
                    if LOG_CAPTURE["enabled"] else "Temporary log capture is disabled."
                ),
                "lines": lines[-MAX_LOG_LINES:],
            }
    if source == "watchers":
        lines = []
        with WATCHERS_LOCK:
            for scope, watcher in WATCHERS.items():
                lines.append(f"[{scope}] watcher")
                lines.extend(watcher.get("output", [])[-160:])
        return {
            "ok": True, "error": None, "source": source,
            "state": "available" if lines else "empty", "enabled": LOG_CAPTURE["enabled"],
            "message": None if lines else (
                "No watcher has produced output yet. Watcher logs are temporary and are cleared when the dashboard restarts."
                if LOG_CAPTURE["enabled"] else "Temporary log capture is disabled."
            ),
            "lines": lines[-MAX_LOG_LINES:],
        }
    raise HTTPException(
        status_code=400,
        detail="source must be memory, code, agentic-rag, dashboard, or watchers",
    )


@app.post("/api/dashboard/logs/reset")
def reset_dashboard_logs(req: LogResetRequest) -> Dict[str, Any]:
    file_sources = {
        "memory": MEMORY_LOG,
        "code": CODE_LOG,
        "agentic-rag": AGENTIC_RAG_LOG,
    }
    if req.source in file_sources:
        path = file_sources[req.source]
        if not path.exists():
            raise HTTPException(status_code=409, detail=f"The {req.source} log file does not exist.")
        try:
            path.write_text("", encoding="utf-8")
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Could not reset {req.source} log: {exc}") from exc
    elif req.source == "dashboard":
        with JOBS_LOCK:
            JOBS.clear()
    elif req.source == "watchers":
        with WATCHERS_LOCK:
            for watcher in WATCHERS.values():
                watcher["output"] = []
    else:
        raise HTTPException(
            status_code=400,
            detail="source must be memory, code, agentic-rag, dashboard, or watchers",
        )
    return {"ok": True, "source": req.source}


@app.post("/api/dashboard/log-capture")
def set_log_capture(req: LogCaptureRequest) -> Dict[str, Any]:
    LOG_CAPTURE["enabled"] = req.enabled
    return {"ok": True, "log_capture": LOG_CAPTURE}


@app.post("/api/dashboard/upload")
def upload_files(scope: str = Form(...), files: List[UploadFile] = File(...)) -> Dict[str, Any]:
    root = scope_root(scope)
    for upload in files:
        validate_upload_extension(scope, upload.filename or "")
    root.mkdir(parents=True, exist_ok=True)
    saved = []
    extracted = []

    for upload in files:
        result = save_upload(upload, root)
        saved.append(result)
        saved_path = root / result["path"]
        if scope == "code" and saved_path.suffix.lower() == ".zip":
            extracted.extend(extract_zip_safe(saved_path, root))

    record_dashboard_event(
        f"upload {scope}",
        [
            f"Uploaded {len(saved)} file(s) to {scope} memory.",
            *[f"{item['path']} ({item['size_bytes']} bytes)" for item in saved],
            *[f"extracted: {path}" for path in extracted],
        ],
    )

    return {"ok": True, "scope": scope, "saved": saved, "extracted": extracted}


@app.post("/api/dashboard/repos/clone")
def clone_repo(req: CloneRequest) -> Dict[str, Any]:
    if not req.repo_url.startswith("https://"):
        raise HTTPException(status_code=400, detail="Only HTTPS repo URLs are supported in the dashboard.")

    repo_name = req.repo_name or infer_repo_name(req.repo_url)
    destination = safe_join(CODE_MEMORY_DIR, repo_name)
    if destination.exists() and not req.update_existing:
        raise HTTPException(status_code=409, detail="Repository destination already exists.")

    CODE_MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    env = build_git_env(req.token)
    if destination.exists() and req.update_existing:
        command = ["git", "-C", str(destination), "pull", "--ff-only"]
        name = f"git pull {repo_name}"
    else:
        command = ["git", "clone", req.repo_url, str(destination)]
        name = f"git clone {repo_name}"

    job = run_job(name=name, command=command, env=env, secrets=[req.token] if req.token else [])
    return {"ok": True, "job": job, "destination": str(destination)}


@app.post("/api/dashboard/index")
def start_index(req: IndexRequest) -> Dict[str, Any]:
    if req.scope == "engineering":
        target = safe_join(ENGINEERING_MEMORY_DIR, req.target)
        command = [PYTHON_BIN, "-m", INDEX_MEMORY_MODULE] + ([] if target == ENGINEERING_MEMORY_DIR else [str(target)])
        env = index_env("engineering-memory", ENGINEERING_MEMORY_DIR)
        name = f"index engineering {req.target or 'all'}"
    elif req.scope == "code":
        target = safe_join(CODE_MEMORY_DIR, req.target)
        command = [PYTHON_BIN, "-m", INDEX_CODE_MODULE, str(target)]
        env = index_env("code-memory", CODE_MEMORY_DIR)
        name = f"index code {req.target or 'all'}"
    else:
        raise HTTPException(status_code=400, detail="scope must be engineering or code")

    if not target.exists():
        raise HTTPException(status_code=404, detail="Index target does not exist.")

    return {"ok": True, "job": run_job(name=name, command=command, env=env)}


@app.get("/api/dashboard/jobs")
def list_jobs() -> Dict[str, Any]:
    with JOBS_LOCK:
        jobs = [job_public(job) for job in JOBS.values()]
    jobs.sort(key=lambda item: item.get("started_at") or "", reverse=True)
    return {"ok": True, "jobs": jobs}


@app.get("/api/dashboard/jobs/{job_id}")
def get_job(job_id: str) -> Dict[str, Any]:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return {"ok": True, "job": job_public(job)}


@app.post("/api/dashboard/watchers/{scope}/start")
def start_watcher(scope: str) -> Dict[str, Any]:
    if scope == "engineering":
        module = WATCH_MEMORY_MODULE
        watched_path = ENGINEERING_MEMORY_DIR
        env = index_env("engineering-memory", ENGINEERING_MEMORY_DIR)
        env["MEMORY_DIR"] = str(ENGINEERING_MEMORY_DIR)
        env["INDEX_MEMORY_MODULE"] = INDEX_MEMORY_MODULE
    elif scope == "code":
        module = WATCH_CODE_MODULE
        watched_path = CODE_MEMORY_DIR
        env = index_env("code-memory", CODE_MEMORY_DIR)
        env["REPOS_ROOT"] = str(CODE_MEMORY_DIR)
        env["INDEX_CODE_MODULE"] = INDEX_CODE_MODULE
    else:
        raise HTTPException(status_code=400, detail="scope must be engineering or code")

    if not watched_path.exists():
        raise HTTPException(status_code=404, detail="Watched directory does not exist.")

    with WATCHERS_LOCK:
        existing = WATCHERS.get(scope)
        if existing and existing.get("process") and existing["process"].poll() is None:
            raise HTTPException(status_code=409, detail=f"{scope} watcher is already running.")

        process = subprocess.Popen(
            [PYTHON_BIN, "-m", module],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        watcher = {
            "process": process,
            "pid": process.pid,
            "started_at": now_iso(),
            "started_ts": time.time(),
            "watched_path": str(watched_path),
            "output": [],
        }
        WATCHERS[scope] = watcher

    def reader() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            if LOG_CAPTURE["enabled"]:
                watcher["output"].append(line.rstrip())
                del watcher["output"][:-MAX_LOG_LINES]

    threading.Thread(target=reader, daemon=True).start()
    return {"ok": True, "watcher": watcher_public(scope, watcher)}


@app.post("/api/dashboard/watchers/{scope}/stop")
def stop_watcher(scope: str) -> Dict[str, Any]:
    with WATCHERS_LOCK:
        watcher = WATCHERS.get(scope)
    if not watcher or not watcher.get("process") or watcher["process"].poll() is not None:
        return {"ok": True, "watcher": {"scope": scope, "running": False}}

    process = watcher["process"]
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)

    return {"ok": True, "watcher": watcher_public(scope, watcher)}


@app.get("/api/dashboard/watchers")
def list_watchers() -> Dict[str, Any]:
    with WATCHERS_LOCK:
        return {
            "ok": True,
            "watchers": {
                "engineering": watcher_public("engineering", WATCHERS.get("engineering")),
                "code": watcher_public("code", WATCHERS.get("code")),
            },
        }


@app.get("/{full_path:path}", include_in_schema=False)
def dashboard_spa_fallback(full_path: str) -> FileResponse:
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not found.")
    return FileResponse(dashboard_index_path())
