#!/usr/bin/env python3
"""Static validation for compute-aware Docker and Compose configuration."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def docker_targets(path: Path) -> set[str]:
    return set(
        filter(
            None,
            re.findall(r"^FROM\s+\S+(?:\s+AS\s+([\w.-]+))?", path.read_text(), re.I | re.M),
        )
    )


def compose_builds(path: Path) -> list[tuple[str, str | None, str | None, bool]]:
    results: list[tuple[str, str | None, str | None, bool]] = []
    service = None
    dockerfile = None
    target = None
    has_backend_arg = False
    in_build = False
    for line in path.read_text(encoding="utf-8").splitlines() + ["  __end__:"]:
        service_match = re.match(r"^  ([\w-]+):\s*$", line)
        if service_match:
            if service is not None and dockerfile is not None:
                results.append((service, dockerfile, target, has_backend_arg))
            service = service_match.group(1)
            dockerfile = target = None
            has_backend_arg = False
            in_build = False
            continue
        if service is None:
            continue
        if re.match(r"^    build:\s*$", line):
            in_build = True
        elif in_build and re.match(r"^    \S", line):
            in_build = False
        if in_build:
            match = re.match(r"^      dockerfile:\s*(\S+)", line)
            if match:
                dockerfile = match.group(1)
            match = re.match(r"^      target:\s*(\S+)", line)
            if match:
                target = match.group(1)
            if re.match(r"^\s+PYTORCH_BACKEND:", line):
                has_backend_arg = True
    return results


def main() -> int:
    errors: list[str] = []
    target_cache: dict[str, set[str]] = {}
    compose_paths = sorted(ROOT.glob("docker-compose*.yml"))
    for path in compose_paths:
        for service, dockerfile, target, has_backend_arg in compose_builds(path):
            docker_path = ROOT / dockerfile
            if not docker_path.is_file():
                errors.append(f"{path.name}:{service}: missing {dockerfile}")
                continue
            targets = target_cache.setdefault(dockerfile, docker_targets(docker_path))
            if target and target not in targets:
                errors.append(f"{path.name}:{service}: target {target!r} not found in {dockerfile}")
            if not has_backend_arg:
                errors.append(f"{path.name}:{service}: build is missing PYTORCH_BACKEND arg")

    for path in (ROOT / "docker").glob("Dockerfile*"):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.match(r"^FROM\s+ai-stack/", line, re.I):
                errors.append(f"{path.relative_to(ROOT)}:{number}: local prerequisite image: {line}")

    neutral_requirements = "\n".join(
        path.read_text(encoding="utf-8") for path in (ROOT / "requirements").glob("*.txt")
    )
    if re.search(r"^\s*torch(?:[<=>\s]|$)", neutral_requirements, re.I | re.M):
        errors.append("neutral requirements must not declare torch")

    expected_gpu_services = {
        "docker-compose.gpu.yml": {"memory-proxy", "code-proxy"},
        "docker-compose.dashboard.gpu.yml": {"dashboard", "indexer"},
        "docker-compose.agentic-rag.gpu.yml": {"agentic-rag"},
    }
    for filename, expected in expected_gpu_services.items():
        text = (ROOT / filename).read_text(encoding="utf-8")
        services = set(re.findall(r"^  ([\w-]+):\s*$", text, re.M))
        if services != expected:
            errors.append(f"{filename}: expected GPU services {sorted(expected)}, found {sorted(services)}")
        if "PYTORCH_BACKEND: ${PYTORCH_BACKEND}" not in text:
            errors.append(f"{filename}: missing resolved CUDA build override")
        if "EMBEDDING_DEVICE: ${EMBEDDING_DEVICE:-cuda}" not in text:
            errors.append(f"{filename}: missing explicit CUDA embedding override")

    base_compute_files = {
        "docker-compose.yml",
        "docker-compose.memory-proxy.yml",
        "docker-compose.code-proxy.yml",
        "docker-compose.dashboard.yml",
        "docker-compose.agentic-rag.yml",
    }
    for filename in base_compute_files:
        text = (ROOT / filename).read_text(encoding="utf-8")
        if "PYTORCH_BACKEND: ${" in text or "EMBEDDING_DEVICE: ${" in text:
            errors.append(f"{filename}: base/standalone compute must remain unconditionally CPU-safe")

    if errors:
        print("Compute configuration validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Compute configuration validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
