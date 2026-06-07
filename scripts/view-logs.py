import json
import os
from pathlib import Path

LOG_FILE = Path("/tmp/memory_api.log")


def show_logs():
    if not LOG_FILE.exists():
        print("❌ No logs found.")
        return

    print("\n📜 --- MEMORY API LOGS ---\n")

    with open(LOG_FILE, "r") as f:
        for line in f:
            try:
                entry = json.loads(line)

                print(f"\n⏱ {entry.get('timestamp')}")
                print(f"🔹 Type: {entry.get('type')}")

                if entry.get("type") == "search_query":
                    print(f"🔍 Query: {entry.get('query')}")

                elif entry.get("type") == "chunk_selected":
                    print(f"📁 File: {entry.get('file')}")
                    print(f"📂 Category: {entry.get('category')}")
                    print(f"⭐ Score: {round(entry.get('score', 0), 3)}")
                    print(f"🧩 Preview: {entry.get('preview')}")

                elif entry.get("type") == "final_context":
                    print(f"🧠 Context count: {entry.get('contexts_count')}")

                elif entry.get("type") == "prompt_built":
                    print(f"🧠 Prompt built for: {entry.get('query')}")
                    print(f"📦 Context size: {entry.get('context_size')}")

                elif entry.get("type") == "model_response":
                    print(f"🤖 Response preview:")
                    print(entry.get("response_preview"))

            except Exception:
                continue


def cleanup():
    choice = input("\n❓ Delete logs? [y/no]: ").strip().lower()

    if choice == "y":
        try:
            os.remove(LOG_FILE)
            print("✅ Logs deleted.")
        except Exception:
            print("⚠️ Could not delete logs.")
    else:
        print("📂 Logs kept.")


if __name__ == "__main__":
    show_logs()
    cleanup()

