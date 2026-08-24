"""Helpers for recognizing explicit document references."""

import re
from pathlib import Path
from typing import Optional


DOCUMENT_EXTENSIONS = "md|txt|json|ya?ml|pdf|docx"


def extract_document_filename(question: str) -> Optional[str]:
    quoted = re.search(
        rf"[\"']([^\"']+\.(?:{DOCUMENT_EXTENSIONS}))[\"']",
        question,
        re.IGNORECASE,
    )
    if quoted:
        return Path(quoted.group(1).strip()).name
    unquoted = re.search(
        rf"\b(?:from|in|file)\s+(.+?\.(?:{DOCUMENT_EXTENSIONS}))(?=\s+(?:and|then|please|explain|list|show|tell)\b|[?.!,]|$)",
        question,
        re.IGNORECASE,
    )
    return Path(unquoted.group(1).strip()).name if unquoted else None
