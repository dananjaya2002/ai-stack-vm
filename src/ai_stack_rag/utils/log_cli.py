"""Interactive memory-RAG log viewer."""

import json
import os
from pathlib import Path

from ai_stack_rag.utils.config import load_settings


LOG_FILE = Path(os.getenv("MEMORY_API_LOG_FILE", load_settings().logging.memory_file))

def show_logs():
    if not LOG_FILE.exists():
        print("❌ No logs found.")
        return

    print("\n📜 ===== MEMORY API DEBUG LOGS =====\n")

    with open(LOG_FILE, "r") as f:
        for line in f:
            try:
                entry = json.loads(line)

                log_type = entry.get("type")

                print("\n" + "=" * 60)
                print(f"⏱ {entry.get('timestamp')}")
                print(f"🔹 Type: {log_type}")

                # -----------------------------
                # SEARCH QUERY
                # -----------------------------
                if log_type == "search_query":
                    print(f"🔍 Query: {entry.get('query')}")

                # -----------------------------
                # ALL CHUNKS SEEN (optional if added)
                # -----------------------------
                elif log_type == "chunk_seen":
                    print(f"📁 File: {entry.get('file')}")
                    print(f"⭐ Score: {round(entry.get('score', 0), 3)}")

                # -----------------------------
                # SELECTED CHUNKS
                # -----------------------------
                elif log_type == "chunk_selected":
                    print(f"📁 File: {entry.get('file')}")
                    print(f"📂 Category: {entry.get('category')}")
                    print(f"⭐ Score: {round(entry.get('score', 0), 3)}")
                    print(f"🧩 Preview:\n{entry.get('preview')}")

                # -----------------------------
                # FINAL CONTEXT (NEW ✅)
                # -----------------------------
                elif log_type == "final_context":
                    print(f"🧠 Query: {entry.get('query')}")
                    print(f"📦 Context count: {entry.get('contexts_count')}")
                    if entry.get("files_used"):
                        print(f"📁 Files used: {entry.get('files_used')}")
                    if entry.get("note"):
                        print(f"📝 Note: {entry.get('note')}")

                # -----------------------------
                # PROMPT BUILT
                # -----------------------------
                elif log_type == "prompt_built":
                    print(f"🧠 Prompt built for: {entry.get('query')}")
                    print(f"📦 Context size: {entry.get('context_size')}")

                # -----------------------------
                # MODEL RESPONSE
                # -----------------------------
                elif log_type == "model_response":
                    print(f"🤖 Response preview:\n{entry.get('response_preview')}")

                # -----------------------------
                # UNKNOWN (fallback)
                # -----------------------------
                else:
                    print(entry)

            except Exception:
                continue


def cleanup():
    print("\n" + "=" * 60)
    choice = input("❓ Delete logs? [y/no]: ").strip().lower()

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
