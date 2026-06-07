import os
import time
import subprocess
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


REPOS_ROOT = Path(os.getenv("REPOS_ROOT", "/repos"))
DEBOUNCE_SECONDS = int(os.getenv("CODE_WATCH_DEBOUNCE_SECONDS", "5"))

pending = {}


class CodeChangeHandler(FileSystemEventHandler):
    def on_modified(self, event):
        handle_event(event)

    def on_created(self, event):
        handle_event(event)

    def on_moved(self, event):
        handle_event(event)


def should_ignore(path: Path) -> bool:
    ignored_parts = {
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
    }

    if set(path.parts).intersection(ignored_parts):
        return True

    if path.name.startswith(".env"):
        return True

    return False


def handle_event(event):
    if event.is_directory:
        return

    path = Path(event.src_path)

    if should_ignore(path):
        return

    pending[str(path)] = time.time()


def process_pending():
    now = time.time()
    ready = [
        path
        for path, changed_at in pending.items()
        if now - changed_at >= DEBOUNCE_SECONDS
    ]

    for path in ready:
        pending.pop(path, None)

        print(f"Indexing changed file: {path}")

        subprocess.run(
            ["python", "/app/index_code.py", path],
            check=False,
        )


def main():
    print(f"Watching code repos: {REPOS_ROOT}")

    observer = Observer()
    observer.schedule(CodeChangeHandler(), str(REPOS_ROOT), recursive=True)
    observer.start()

    try:
        while True:
            process_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()

    observer.join()


if __name__ == "__main__":
    main()
