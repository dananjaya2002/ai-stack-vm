import time
from pathlib import Path
import threading

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

import subprocess


# CONFIG
MEMORY_DIR = Path.home() / "ai-stack/memory/engineering-memory"

DEBOUNCE_SECONDS = 5   # wait after last change
MIN_FILE_SIZE = 5      # ignore tiny temp writes



class MemoryChangeHandler(FileSystemEventHandler):
    def __init__(self):
        self.timer = None
        self.lock = threading.Lock()
        self.last_file = None

    def should_ignore(self, event):
        if event.is_directory:
            return True

        path = Path(event.src_path)

        if path.name.startswith("."):
            return True

        return False

    def schedule_index(self, file_path):
        with self.lock:
            if self.timer:
                self.timer.cancel()

            self.last_file = file_path

            self.timer = threading.Timer(
                DEBOUNCE_SECONDS,
                lambda: self.run_index(self.last_file)
            )
            self.timer.start()

            print(f"⏳ Change detected: {file_path}")


    def run_index(self, file_path):
        print(f"\n📂 Incremental indexing → {file_path}\n")

        subprocess.run([
            str(Path.home() / "ai-stack/python-envs/qdrant-env/bin/python"),
            str(Path.home() / "ai-stack/scripts/memory-proxy/index_memory.py"),
            file_path
        ])

    
    def on_modified(self, event):
        if not self.should_ignore(event):
            self.schedule_index(event.src_path)

    def on_created(self, event):
        if not self.should_ignore(event):
            self.schedule_index(event.src_path)

    def on_deleted(self, event):
        if not self.should_ignore(event):
            self.schedule_index(event.src_path)



def main():
    print(f"👀 Watching memory folder: {MEMORY_DIR}")
    print(f"⏳ Debounce mode: waiting {DEBOUNCE_SECONDS}s after changes\n")

    event_handler = MemoryChangeHandler()
    observer = Observer()

    observer.schedule(event_handler, str(MEMORY_DIR), recursive=True)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Stopping watcher...")
        observer.stop()

    observer.join()


if __name__ == "__main__":
    main()
