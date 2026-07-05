import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import psutil
import requests
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
FRONTEND_DIST_DIR = BASE_DIR / "frontend" / "dist"

load_dotenv()
load_dotenv(BASE_DIR / "dashboard.env", override=False)

LLAMA_BASE_URL = os.getenv("LLAMA_BASE_URL", "http://localhost:8082/v1").rstrip("/")
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333").rstrip("/")
QDRANT_HOST = os.getenv("QDRANT_HOST", "qdrant")
QDRANT_PORT = os.getenv("QDRANT_PORT", "6333")

ENGINEERING_MEMORY_DIR = Path(os.getenv("ENGINEERING_MEMORY_DIR", "/memory/engineering-memory"))
CODE_MEMORY_DIR = Path(os.getenv("CODE_MEMORY_DIR", "/memory/code-memory"))
MEMORY_LOG = Path(os.getenv("MEMORY_LOG", "/logs/memory/memory_api.log"))
CODE_LOG = Path(os.getenv("CODE_LOG", "/logs/code/code_proxy.log"))
DASHBOARD_LOG_DIR = Path(os.getenv("DASHBOARD_LOG_DIR", "/tmp/ai-stack-dashboard"))

INDEX_MEMORY_SCRIPT = Path(os.getenv("INDEX_MEMORY_SCRIPT", "/app/memory-proxy/index_memory.py"))
INDEX_CODE_SCRIPT = Path(os.getenv("INDEX_CODE_SCRIPT", "/app/watcher/index_code.py"))
WATCH_MEMORY_SCRIPT = Path(os.getenv("WATCH_MEMORY_SCRIPT", "/app/memory-proxy/watch_memory.py"))
WATCH_CODE_SCRIPT = Path(os.getenv("WATCH_CODE_SCRIPT", "/app/watcher/watch_code.py"))
PYTHON_BIN = os.getenv("PYTHON_BIN", "python")

HTTP_TIMEOUT_SECONDS = float(os.getenv("DASHBOARD_HTTP_TIMEOUT_SECONDS", "3"))
MAX_LOG_LINES = int(os.getenv("DASHBOARD_MAX_LOG_LINES", "400"))
MAX_UPLOAD_BYTES = int(os.getenv("DASHBOARD_MAX_UPLOAD_BYTES", str(100 * 1024 * 1024)))

app = FastAPI(title="AI Stack Dashboard")

if (FRONTEND_DIST_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST_DIR / "assets"), name="assets")
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

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


class DeleteFileRequest(BaseModel):
    scope: str
    path: str


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
        return error_payload(str(exc), base_url=LLAMA_BASE_URL, latency_ms=None, approximate_token_speed=None)

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
            "warning": True,
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
            "warning": False,
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


def read_last_lines(path: Path, max_lines: int = MAX_LOG_LINES) -> Dict[str, Any]:
    if not path.exists():
        return {"ok": False, "error": "Log file does not exist.", "path": str(path), "lines": []}
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return {"ok": True, "error": None, "path": str(path), "lines": lines[-max_lines:]}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "path": str(path), "lines": []}


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
        raise HTTPException(status_code=404, detail="File does not exist.")
    if not target.is_file():
        raise HTTPException(status_code=400, detail="Only files can be deleted.")

    size_bytes = target.stat().st_size
    target.unlink()

    record_dashboard_event(
        f"delete {scope}",
        [
            f"Deleted {relative_path} from {scope} memory.",
            f"Size: {size_bytes} bytes",
        ],
    )
    return {"ok": True, "scope": scope, "path": relative_path, "size_bytes": size_bytes}


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
    return STATIC_DIR / "index.html"


@app.get("/")
def dashboard_home() -> FileResponse:
    return FileResponse(dashboard_index_path())


@app.get("/api/dashboard/status")
def dashboard_status() -> Dict[str, Any]:
    llama = check_llama()
    qdrant = check_qdrant()
    memories = {"engineering": memory_stats(ENGINEERING_MEMORY_DIR), "code": memory_stats(CODE_MEMORY_DIR)}
    logs = {"memory": log_stats(MEMORY_LOG), "code": log_stats(CODE_LOG)}
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


@app.get("/api/dashboard/files")
def dashboard_files(scope: str) -> Dict[str, Any]:
    return list_files(scope)


@app.delete("/api/dashboard/files")
def dashboard_delete_file(req: DeleteFileRequest) -> Dict[str, Any]:
    return delete_memory_file(req.scope, req.path)


@app.get("/api/dashboard/logs")
def dashboard_logs(source: str = "dashboard") -> Dict[str, Any]:
    if source == "memory":
        return read_last_lines(MEMORY_LOG)
    if source == "code":
        return read_last_lines(CODE_LOG)
    if source == "dashboard":
        with JOBS_LOCK:
            lines = []
            for job in JOBS.values():
                lines.append(f"[{job['status']}] {job['name']} {job['id']}")
                lines.extend(job.get("output", [])[-80:])
            return {"ok": True, "error": None, "source": source, "lines": lines[-MAX_LOG_LINES:]}
    if source == "watchers":
        lines = []
        with WATCHERS_LOCK:
            for scope, watcher in WATCHERS.items():
                lines.append(f"[{scope}] watcher")
                lines.extend(watcher.get("output", [])[-160:])
        return {"ok": True, "error": None, "source": source, "lines": lines[-MAX_LOG_LINES:]}
    raise HTTPException(status_code=400, detail="source must be memory, code, dashboard, or watchers")


@app.post("/api/dashboard/log-capture")
def set_log_capture(req: LogCaptureRequest) -> Dict[str, Any]:
    LOG_CAPTURE["enabled"] = req.enabled
    return {"ok": True, "log_capture": LOG_CAPTURE}


@app.post("/api/dashboard/upload")
def upload_files(scope: str = Form(...), files: List[UploadFile] = File(...)) -> Dict[str, Any]:
    root = scope_root(scope)
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
        command = [PYTHON_BIN, str(INDEX_MEMORY_SCRIPT)] + ([] if target == ENGINEERING_MEMORY_DIR else [str(target)])
        env = index_env("engineering-memory", ENGINEERING_MEMORY_DIR)
        name = f"index engineering {req.target or 'all'}"
    elif req.scope == "code":
        target = safe_join(CODE_MEMORY_DIR, req.target)
        command = [PYTHON_BIN, str(INDEX_CODE_SCRIPT), str(target)]
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
        script = WATCH_MEMORY_SCRIPT
        watched_path = ENGINEERING_MEMORY_DIR
        env = index_env("engineering-memory", ENGINEERING_MEMORY_DIR)
        env["MEMORY_DIR"] = str(ENGINEERING_MEMORY_DIR)
        env["INDEX_MEMORY_SCRIPT"] = str(INDEX_MEMORY_SCRIPT)
    elif scope == "code":
        script = WATCH_CODE_SCRIPT
        watched_path = CODE_MEMORY_DIR
        env = index_env("code-memory", CODE_MEMORY_DIR)
        env["REPOS_ROOT"] = str(CODE_MEMORY_DIR)
        env["INDEX_CODE_SCRIPT"] = str(INDEX_CODE_SCRIPT)
    else:
        raise HTTPException(status_code=400, detail="scope must be engineering or code")

    if not watched_path.exists():
        raise HTTPException(status_code=404, detail="Watched directory does not exist.")

    with WATCHERS_LOCK:
        existing = WATCHERS.get(scope)
        if existing and existing.get("process") and existing["process"].poll() is None:
            raise HTTPException(status_code=409, detail=f"{scope} watcher is already running.")

        process = subprocess.Popen(
            [PYTHON_BIN, str(script)],
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
