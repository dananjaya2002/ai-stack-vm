"""Compatibility loaders for the legacy JSON rule files."""

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List


def default_config_path(env_name: str, filename: str, current_file: str) -> Path:
    override = os.getenv(env_name)
    if override:
        return Path(override)

    script_path = Path(current_file).resolve()
    candidates = [script_path.with_name(filename)]
    for parent in script_path.parents:
        candidates.extend(
            [
                parent / "config" / filename,
                parent / "scripts" / "config" / filename,
            ]
        )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[1]


def load_json_object(path: Path, config_name: str) -> Dict[str, Any]:
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Unable to load {config_name} config: {path}") from exc
    if not isinstance(config, dict):
        raise RuntimeError(f"{config_name} config must be a JSON object: {path}")
    return config


def require_string_set(
    config: Dict[str, Any],
    key: str,
    config_name: str,
    *,
    lowercase: bool = False,
) -> set[str]:
    value = config.get(key)
    if not isinstance(value, list):
        raise RuntimeError(f"{config_name} config key must be a list: {key}")
    items = {
        str(item).strip().lower() if lowercase else str(item).strip()
        for item in value
        if str(item).strip()
    }
    if not items:
        raise RuntimeError(f"{config_name} config key must not be empty: {key}")
    return items


def require_string_map(config: Dict[str, Any], key: str, config_name: str) -> Dict[str, str]:
    value = config.get(key)
    if not isinstance(value, dict) or not value:
        raise RuntimeError(f"{config_name} config key must be a non-empty object: {key}")
    items = {
        str(map_key).strip().lower(): str(map_value).strip()
        for map_key, map_value in value.items()
        if str(map_key).strip() and str(map_value).strip()
    }
    if not items:
        raise RuntimeError(f"{config_name} config key must not be empty: {key}")
    return items


def require_string_sets(
    config: Dict[str, Any],
    keys: List[str],
    config_name: str,
    *,
    lowercase: bool = False,
) -> Dict[str, set[str]]:
    missing_keys = [key for key in keys if key not in config]
    if missing_keys:
        raise RuntimeError(
            f"{config_name} config is missing required keys: {', '.join(missing_keys)}"
        )
    return {
        key: require_string_set(config, key, config_name, lowercase=lowercase)
        for key in keys
    }


def compile_regex_flags(flag_names: List[str], config_name: str) -> int:
    flags = 0
    for flag_name in flag_names:
        try:
            flags |= getattr(re, flag_name)
        except AttributeError as exc:
            raise RuntimeError(f"Unsupported regex flag in {config_name} config: {flag_name}") from exc
    return flags


def require_symbol_patterns(
    config: Dict[str, Any],
    key: str,
    config_name: str,
) -> Dict[str, List[tuple[str, re.Pattern[str]]]]:
    raw_patterns = config.get(key)
    if not isinstance(raw_patterns, dict) or not raw_patterns:
        raise RuntimeError(f"{config_name} config key must be a non-empty object: {key}")

    compiled_patterns: Dict[str, List[tuple[str, re.Pattern[str]]]] = {}
    for language, patterns in raw_patterns.items():
        if not isinstance(patterns, list):
            raise RuntimeError(f"Symbol patterns for {language} must be a list")

        compiled_patterns[str(language)] = []
        for entry in patterns:
            if not isinstance(entry, dict):
                raise RuntimeError(f"Symbol pattern entry for {language} must be an object")
            symbol_type = str(entry.get("type") or "").strip()
            pattern = str(entry.get("pattern") or "")
            raw_flags = entry.get("flags", [])
            if not isinstance(raw_flags, list):
                raise RuntimeError(f"Symbol pattern flags for {language}.{symbol_type} must be a list")
            if not symbol_type or not pattern:
                raise RuntimeError(f"Symbol pattern entry for {language} requires type and pattern")
            compiled_patterns[str(language)].append(
                (
                    symbol_type,
                    re.compile(pattern, compile_regex_flags([str(flag) for flag in raw_flags], config_name)),
                )
            )
    return compiled_patterns
