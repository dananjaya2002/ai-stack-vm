
import os
import sys
import time
import subprocess
from pathlib import Path

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


# -----------------------------
# Configuration
# -----------------------------

REPOS_ROOT = Path(os.getenv("REPOS_ROOT", "/memory/code-memory"))

INDEX_CODE_SCRIPT = Path(
    os.getenv("INDEX_CODE_SCRIPT", "/app/code-proxy/index_code.py")
)

PYTHON_BIN = os.getenv("PYTHON_BIN", sys.executable)

QDRANT_COLLECTION = os.getenv(
    "CODE_QDRANT_COLLECTION",
    os.getenv("QDRANT_COLLECTION", "code-memory")
)

DEBOUNCE_SECONDS = int(os.getenv("CODE_WATCH_DEBOUNCE_SECONDS", "5"))


# -----------------------------
# Ignore rules
# -----------------------------

IGNORED_DIRS = {
    ".git",
    "node_modules",
    "dist",
    "build",
    "target",
    ".next",
    ".nuxt",
    "coverage",
    "__pycache__",
    ".venv",
    "venv",
    ".idea",
    ".vscode",
}

IGNORED_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".log",
    ".tmp",
    ".swp",
    ".part",
    ".lock",
    ".map",
}

IGNORED_NAMES = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
}


pending = {}


def should_ignore(path: Path) -> bool:
    if set(path.parts).intersection(IGNORED_DIRS):
        return True

    if path.name in IGNORED_NAMES:
        return True

    if path.name.startswith(".env"):
        return True

    if path.name.startswith(".") and path.name not in {".gitignore"}:
        return True

    if path.suffix in IGNORED_SUFFIXES:
        return True

    return False


# -----------------------------
# Watch handler
# -----------------------------

class CodeChangeHandler(FileSystemEventHandler):
    def on_modified(self, event):
        handle_event(event)

    def on_created(self, event):
        handle_event(event)

    def on_moved(self, event):
        if event.is_directory:
            return

        dest_path = getattr(event, "dest_path", None)
        if dest_path:
            handle_path(dest_path)

    def on_deleted(self, event):
        if event.is_directory:
            return

        path = Path(event.src_path)
        if should_ignore(path):
            return

        print(f"🗑️ Code file deleted: {path}", flush=True)


def handle_event(event):
    if event.is_directory:
        return

    handle_path(event.src_path)


def handle_path(raw_path):
    path = Path(raw_path)

    if should_ignore(path):
        return

    pending[str(path)] = time.time()
    print(f"⏳ Code change detected: {path}", flush=True)


def process_pending():
    now = time.time()

    ready = [
        path
        for path, changed_at in list(pending.items())
        if now - changed_at >= DEBOUNCE_SECONDS
    ]

    for path in ready:
        pending.pop(path, None)

        file_path = Path(path)

        if not file_path.exists():
            print(f"🗑️ Code file missing, skipping direct index: {file_path}", flush=True)
            continue

        print(f"\n📂 Incremental code indexing → {file_path}\n", flush=True)

        env = os.environ.copy()
        env["QDRANT_COLLECTION"] = QDRANT_COLLECTION

        result = subprocess.run(
            [
                PYTHON_BIN,
                str(INDEX_CODE_SCRIPT),
                str(file_path),
            ],
            env=env,
            check=False,
        )

        if result.returncode != 0:
            print(
                f"❌ Code indexing failed for {file_path} with exit code {result.returncode}",
                flush=True,
            )
        else:
            print(f"✅ Code indexing complete: {file_path}", flush=True)


# -----------------------------
# Main
# -----------------------------

def main():
    print("========================================", flush=True)
    print("Code watcher", flush=True)
    print("========================================", flush=True)
    print(f"Watching code repos: {REPOS_ROOT}", flush=True)
    print(f"Index script: {INDEX_CODE_SCRIPT}", flush=True)
    print(f"Python: {PYTHON_BIN}", flush=True)
    print(f"Qdrant collection: {QDRANT_COLLECTION}", flush=True)
    print(f"Debounce seconds: {DEBOUNCE_SECONDS}", flush=True)
    print("========================================", flush=True)

    if not REPOS_ROOT.exists():
        print(f"❌ Code repos root does not exist: {REPOS_ROOT}", flush=True)
        sys.exit(1)

    if not INDEX_CODE_SCRIPT.exists():
        print(f"❌ index_code.py not found: {INDEX_CODE_SCRIPT}", flush=True)
        sys.exit(1)

    observer = Observer()
    observer.schedule(CodeChangeHandler(), str(REPOS_ROOT), recursive=True)
    observer.start()

    try:
        while True:
            process_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Stopping code watcher...", flush=True)
        observer.stop()

    observer.join()


if __name__ == "__main__":
    main()
