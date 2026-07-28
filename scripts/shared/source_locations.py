import re
from pathlib import PurePosixPath
from typing import Any, Iterable, Optional


SOURCE_MARKER_RE = re.compile(r"\[/?\s*source\s+(\d+)\s*\]", re.IGNORECASE)
SOURCE_HEADING_RE = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:sources?|source locations?)\s*:?\s*$",
    re.IGNORECASE,
)


def _normalized_parts(value: Any) -> list[str]:
    normalized = str(value or "").strip().replace("\\", "/")
    normalized = re.sub(r"^[A-Za-z]:", "", normalized)
    return [part for part in normalized.split("/") if part not in {"", ".", ".."}]


def canonical_source_path(
    source_type: str,
    *,
    repo_name: Optional[str] = None,
    relative_path: Any = None,
    file_path: Any = None,
    source_path: Any = None,
) -> str:
    raw_path = source_path or relative_path or file_path or "unknown"
    raw_text = str(raw_path or "").strip().replace("\\", "/")
    is_absolute = raw_text.startswith("/") or bool(re.match(r"^[A-Za-z]:/", raw_text))
    parts = _normalized_parts(raw_path)

    if source_type == "memory":
        return parts[-1] if parts else "unknown"

    repo = str(repo_name or "").strip().replace("\\", "/").strip("/")
    if not repo:
        return "/".join(parts) if parts else "unknown"

    repo_index = next(
        (index for index, part in enumerate(parts) if part.casefold() == repo.casefold()),
        None,
    )
    if repo_index is not None:
        parts = parts[repo_index + 1 :]
    elif is_absolute and parts:
        parts = parts[-1:]

    while parts and parts[0].casefold() == repo.casefold():
        parts = parts[1:]

    relative = "/".join(parts)
    return f"{repo}/{relative}" if relative else repo


def format_source_location(
    source_type: str,
    *,
    repo_name: Optional[str] = None,
    relative_path: Any = None,
    file_path: Any = None,
    source_path: Any = None,
    line_start: Any = None,
    line_end: Any = None,
    chunk_index: Any = None,
) -> str:
    path = canonical_source_path(
        source_type,
        repo_name=repo_name,
        relative_path=relative_path,
        file_path=file_path,
        source_path=source_path,
    )
    if source_type == "memory":
        return PurePosixPath(path).name
    if line_start and line_end:
        return f"{path}:{line_start}-{line_end}"
    if line_start:
        return f"{path}:{line_start}"
    if chunk_index is not None:
        return f"{path}#chunk-{chunk_index}"
    return path


def clean_source_markers(text: str, locations: Iterable[str]) -> str:
    location_list = list(locations)
    lines = str(text or "").splitlines()
    for index, line in enumerate(lines):
        if not SOURCE_HEADING_RE.match(line):
            continue
        trailing = "\n".join(lines[index + 1 :])
        if SOURCE_MARKER_RE.search(trailing):
            lines = lines[:index]
            break
    cleaned = "\n".join(lines)

    def replace_marker(match: re.Match[str]) -> str:
        if match.group(0).lstrip().startswith("[/"):
            return ""
        source_index = int(match.group(1)) - 1
        if 0 <= source_index < len(location_list):
            return f"`{location_list[source_index]}`"
        return ""

    cleaned = SOURCE_MARKER_RE.sub(replace_marker, cleaned)
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    return cleaned.strip()
