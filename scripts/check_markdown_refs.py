#!/usr/bin/env python3
"""Check local Markdown links and stale documentation references."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_FILES = [ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]
LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
STALE_REFERENCES = (
    "dashboard.env",
    "code-proxy.env",
    "memory-api.env",
    "agentic-rag.env.example",
)


def is_external(target: str) -> bool:
    lowered = target.lower()
    return lowered.startswith(("http://", "https://", "mailto:", "tel:"))


def clean_target(raw_target: str) -> str:
    target = raw_target.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    return target.split("#", 1)[0].strip()


def check_links() -> list[str]:
    errors: list[str] = []
    for markdown_file in MARKDOWN_FILES:
        text = markdown_file.read_text(encoding="utf-8")
        for raw_target in LINK_RE.findall(text):
            target = clean_target(raw_target)
            if not target or is_external(target):
                continue
            if target.startswith("#"):
                continue
            candidate = (markdown_file.parent / unquote(target)).resolve()
            try:
                candidate.relative_to(ROOT)
            except ValueError:
                errors.append(f"{markdown_file.relative_to(ROOT)} links outside repo: {raw_target}")
                continue
            if not candidate.exists():
                errors.append(f"{markdown_file.relative_to(ROOT)} has missing link: {raw_target}")
    return errors


def check_stale_references() -> list[str]:
    errors: list[str] = []
    for markdown_file in MARKDOWN_FILES:
        text = markdown_file.read_text(encoding="utf-8")
        for stale in STALE_REFERENCES:
            if stale in text:
                errors.append(f"{markdown_file.relative_to(ROOT)} contains stale reference: {stale}")
    return errors


def main() -> int:
    errors = check_links() + check_stale_references()
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print(f"checked {len(MARKDOWN_FILES)} Markdown files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
