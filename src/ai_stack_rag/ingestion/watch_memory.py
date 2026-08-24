"""Watch engineering-memory files and invoke incremental ingestion."""

import os
import sys
import time
import threading
import subprocess
from pathlib import Path

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from ai_stack_rag.utils.legacy_config import default_config_path, load_json_object, require_string_set


# -----------------------------
# Configuration
# -----------------------------

MEMORY_DIR = Path(
    os.getenv(
        "MEMORY_DIR",
        os.getenv("MEMORY_ROOT", "/memory/engineering-memory")
    )
)

INDEX_MEMORY_MODULE = os.getenv("INDEX_MEMORY_MODULE", "ai_stack_rag.ingestion.memory")

PYTHON_BIN = os.getenv("PYTHON_BIN", sys.executable)

QDRANT_COLLECTION = os.getenv(
    "MEMORY_QDRANT_COLLECTION",
    os.getenv("QDRANT_COLLECTION", "engineering-memory")
)

DEBOUNCE_SECONDS = int(os.getenv("MEMORY_WATCH_DEBOUNCE_SECONDS", "5"))
MIN_FILE_SIZE = int(os.getenv("MEMORY_WATCH_MIN_FILE_SIZE", "5"))
MEMORY_WATCH_CONFIG_FILE = default_config_path("MEMORY_WATCH_CONFIG_FILE", "memory_watch.json", __file__)
MEMORY_WATCH_CONFIG = load_json_object(MEMORY_WATCH_CONFIG_FILE, "Memory watch")


# -----------------------------
# Ignore rules
# -----------------------------

IGNORED_DIRS = require_string_set(MEMORY_WATCH_CONFIG, "ignored_dirs", "Memory watch")
IGNORED_SUFFIXES = require_string_set(MEMORY_WATCH_CONFIG, "ignored_suffixes", "Memory watch", lowercase=True)


def should_ignore_path(path: Path) -> bool:
    if set(path.parts).intersection(IGNORED_DIRS):
        return True

    if path.name.startswith("."):
        return True

    if path.suffix.lower() in IGNORED_SUFFIXES:
        return True

    return False


# -----------------------------
# Watch handler
# -----------------------------

class MemoryChangeHandler(FileSystemEventHandler):
    def __init__(self):
        self.lock = threading.Lock()
        self.timers = {}

    def should_ignore(self, event) -> bool:
        if event.is_directory:
            return True

        path = Path(event.src_path)
        return should_ignore_path(path)

    def schedule_index(self, file_path: str):
        path = Path(file_path)

        if should_ignore_path(path):
            return

        with self.lock:
            key = str(path)

            old_timer = self.timers.get(key)
            if old_timer:
                old_timer.cancel()

            timer = threading.Timer(
                DEBOUNCE_SECONDS,
                lambda: self.run_index(key)
            )

            self.timers[key] = timer
            timer.start()

            print(f"⏳ Memory change detected: {key}", flush=True)

    def run_index(self, file_path: str):
        path = Path(file_path)

        with self.lock:
            self.timers.pop(file_path, None)

        if not path.exists():
            print(f"🗑️ Memory file deleted or missing, skipping direct index: {file_path}", flush=True)
            return

        if path.is_file() and path.stat().st_size < MIN_FILE_SIZE:
            print(f"⚠️ Memory file too small, skipping: {file_path}", flush=True)
            return

        print(f"\n📂 Incremental memory indexing → {file_path}\n", flush=True)

        env = os.environ.copy()
        env["QDRANT_COLLECTION"] = QDRANT_COLLECTION

        result = subprocess.run(
            [
                PYTHON_BIN,
                "-m",
                INDEX_MEMORY_MODULE,
                file_path,
            ],
            env=env,
            check=False,
        )

        if result.returncode != 0:
            print(
                f"❌ Memory indexing failed for {file_path} with exit code {result.returncode}",
                flush=True,
            )
        else:
            print(f"✅ Memory indexing complete: {file_path}", flush=True)

    def on_modified(self, event):
        if not self.should_ignore(event):
            self.schedule_index(event.src_path)

    def on_created(self, event):
        if not self.should_ignore(event):
            self.schedule_index(event.src_path)

    def on_moved(self, event):
        if event.is_directory:
            return

        dest_path = getattr(event, "dest_path", None)
        if dest_path:
            self.schedule_index(dest_path)

    def on_deleted(self, event):
        if not self.should_ignore(event):
            print(f"🗑️ Memory file deleted: {event.src_path}", flush=True)


# -----------------------------
# Main
# -----------------------------

def main():
    print("========================================", flush=True)
    print("Memory watcher", flush=True)
    print("========================================", flush=True)
    print(f"Watching memory folder: {MEMORY_DIR}", flush=True)
    print(f"Index module: {INDEX_MEMORY_MODULE}", flush=True)
    print(f"Python: {PYTHON_BIN}", flush=True)
    print(f"Qdrant collection: {QDRANT_COLLECTION}", flush=True)
    print(f"Debounce seconds: {DEBOUNCE_SECONDS}", flush=True)
    print("========================================", flush=True)

    if not MEMORY_DIR.exists():
        print(f"❌ Memory directory does not exist: {MEMORY_DIR}", flush=True)
        sys.exit(1)

    event_handler = MemoryChangeHandler()
    observer = Observer()

    observer.schedule(event_handler, str(MEMORY_DIR), recursive=True)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Stopping memory watcher...", flush=True)
        observer.stop()

    observer.join()


if __name__ == "__main__":
    main()
