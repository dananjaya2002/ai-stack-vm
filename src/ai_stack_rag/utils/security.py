"""Shared validation and request security middleware."""

import os
import sys
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Iterable, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


def _env_bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _require_non_empty(errors: list[str], name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        errors.append(name)
    return value


def _require_int(errors: list[str], name: str, default: str, minimum: int = 1) -> int:
    value = os.getenv(name, default).strip()
    try:
        parsed = int(value)
    except ValueError:
        errors.append(f"{name} must be an integer")
        return minimum

    if parsed < minimum:
        errors.append(f"{name} must be >= {minimum}")
    return parsed


def validate_proxy_environment(
    service_name: str,
    required_vars: Iterable[str],
    required_paths: Optional[Iterable[str]] = None,
) -> None:
    errors: list[str] = []

    security_mode = os.getenv("SECURITY_MODE", "development").strip().lower()
    api_key = os.getenv("AI_STACK_API_KEY", "").strip()

    if security_mode not in {"development", "production"}:
        errors.append("SECURITY_MODE must be development or production")

    for name in required_vars:
        _require_non_empty(errors, name)

    _require_int(errors, "QDRANT_PORT", "6333")
    _require_int(errors, "RATE_LIMIT_PER_MINUTE", "60")

    if security_mode == "production" and not api_key:
        errors.append("AI_STACK_API_KEY is required when SECURITY_MODE=production")

    if required_paths:
        for raw_path in required_paths:
            path = Path(os.getenv(raw_path, "") or raw_path)
            if not path.exists():
                errors.append(f"{raw_path} path does not exist: {path}")

    if errors:
        print(f"{service_name} configuration error:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        raise SystemExit(1)

    if security_mode == "development" and not api_key:
        print(
            f"{service_name} warning: AI_STACK_API_KEY is empty; "
            "unauthenticated development access is enabled.",
            file=sys.stderr,
        )


def install_security_middleware(app: FastAPI, service_name: str) -> None:
    security_mode = os.getenv("SECURITY_MODE", "development").strip().lower()
    api_key = os.getenv("AI_STACK_API_KEY", "").strip()
    enable_rate_limit = _env_bool("ENABLE_RATE_LIMIT", "true")
    rate_limit_per_minute = _require_int([], "RATE_LIMIT_PER_MINUTE", "60")
    request_times: dict[str, deque[float]] = defaultdict(deque)

    @app.middleware("http")
    async def security_middleware(request: Request, call_next):
        if api_key:
            expected = f"Bearer {api_key}"
            if request.headers.get("authorization", "") != expected:
                return JSONResponse(
                    status_code=401,
                    content={"error": "Unauthorized"},
                    headers={"WWW-Authenticate": "Bearer"},
                )
        elif security_mode == "production":
            return JSONResponse(
                status_code=401,
                content={"error": "AI_STACK_API_KEY is required in production"},
            )

        if enable_rate_limit:
            client_ip = request.client.host if request.client else "unknown"
            now = time.monotonic()
            window_start = now - 60
            history = request_times[client_ip]

            while history and history[0] < window_start:
                history.popleft()

            if len(history) >= rate_limit_per_minute:
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "Rate limit exceeded",
                        "detail": f"Limit is {rate_limit_per_minute} requests per minute.",
                    },
                )

            history.append(now)

        return await call_next(request)
