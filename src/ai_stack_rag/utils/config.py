"""Typed configuration with YAML defaults and environment overrides."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml


@dataclass(frozen=True)
class IngestionSettings:
    memory_root: str = "/memory"
    code_root: str = "/code-memory"


@dataclass(frozen=True)
class ChunkingSettings:
    memory_size: int = 500
    code_max_chars: int = 2200
    code_overlap_chars: int = 300


@dataclass(frozen=True)
class EmbeddingSettings:
    model: str = "all-MiniLM-L6-v2"
    device: str = "cpu"


@dataclass(frozen=True)
class VectorDBSettings:
    host: str = "localhost"
    port: int = 6333
    memory_collection: str = "engineering-memory"
    code_collection: str = "code-memory"


@dataclass(frozen=True)
class RetrievalSettings:
    simple_top_k: int = 6
    score_threshold: float = 0.20
    max_chunks_per_file: int = 2
    max_chunk_chars: int = 4000
    max_context_chars: int = 50000


@dataclass(frozen=True)
class LLMSettings:
    base_url: str = "http://localhost:8082/v1"
    model: str = "qwen2.5-coder-7b-instruct-q4_k_m.gguf"
    timeout_seconds: int = 300


@dataclass(frozen=True)
class AgenticSettings:
    enabled: bool = True
    max_steps: int = 4
    initial_subqueries: int = 3
    followup_top_k: int = 4
    max_total_chunks: int = 16
    min_confidence: float = 0.70
    top_k_per_query: int = 3


@dataclass(frozen=True)
class LoggingSettings:
    enabled: bool = True
    memory_file: str = "/logs/memory/memory_api.log"
    code_file: str = "/logs/code/code_proxy.log"
    agentic_file: str = "/logs/agentic-rag/agentic_rag.log"


@dataclass(frozen=True)
class WatcherSettings:
    memory_rules_file: str = "config/memory_watch.json"
    code_rules_file: str = "config/code_watch.json"
    code_index_rules_file: str = "config/code_index.json"
    agentic_terms_file: str = "config/agentic_rag_terms.json"


@dataclass(frozen=True)
class Settings:
    ingestion: IngestionSettings
    chunking: ChunkingSettings
    embeddings: EmbeddingSettings
    vector_db: VectorDBSettings
    retrieval: RetrievalSettings
    llm: LLMSettings
    agentic: AgenticSettings
    logging: LoggingSettings
    watchers: WatcherSettings


ENV_OVERRIDES: dict[str, tuple[str, str, type]] = {
    "MEMORY_PATH": ("ingestion", "memory_root", str),
    "CODE_MEMORY_PATH": ("ingestion", "code_root", str),
    "CHUNK_SIZE": ("chunking", "memory_size", int),
    "CHUNK_MAX_CHARS": ("chunking", "code_max_chars", int),
    "CHUNK_OVERLAP_CHARS": ("chunking", "code_overlap_chars", int),
    "EMBED_MODEL_NAME": ("embeddings", "model", str),
    "EMBEDDING_DEVICE": ("embeddings", "device", str),
    "QDRANT_HOST": ("vector_db", "host", str),
    "QDRANT_PORT": ("vector_db", "port", int),
    "MEMORY_COLLECTION": ("vector_db", "memory_collection", str),
    "MEMORY_QDRANT_COLLECTION": ("vector_db", "memory_collection", str),
    "CODE_COLLECTION": ("vector_db", "code_collection", str),
    "SIMPLE_TOP_K": ("retrieval", "simple_top_k", int),
    "AGENTIC_SCORE_THRESHOLD": ("retrieval", "score_threshold", float),
    "MAX_CHUNKS_PER_FILE": ("retrieval", "max_chunks_per_file", int),
    "MAX_CHUNK_CHARS": ("retrieval", "max_chunk_chars", int),
    "MAX_CONTEXT_CHARS": ("retrieval", "max_context_chars", int),
    "LLM_BASE_URL": ("llm", "base_url", str),
    "LLM_MODEL": ("llm", "model", str),
    "AGENTIC_MAX_STEPS": ("agentic", "max_steps", int),
    "AGENTIC_INITIAL_SUBQUERIES": ("agentic", "initial_subqueries", int),
    "AGENTIC_FOLLOWUP_TOP_K": ("agentic", "followup_top_k", int),
    "AGENTIC_MAX_TOTAL_CHUNKS": ("agentic", "max_total_chunks", int),
    "AGENTIC_MIN_CONFIDENCE": ("agentic", "min_confidence", float),
    "AGENTIC_TOP_K_PER_QUERY": ("agentic", "top_k_per_query", int),
    "MEMORY_API_LOG_FILE": ("logging", "memory_file", str),
    "CODE_PROXY_LOG_FILE": ("logging", "code_file", str),
    "AGENTIC_RAG_LOG_FILE": ("logging", "agentic_file", str),
    "MEMORY_WATCH_CONFIG_FILE": ("watchers", "memory_rules_file", str),
    "CODE_WATCH_CONFIG_FILE": ("watchers", "code_rules_file", str),
    "CODE_INDEX_CONFIG_FILE": ("watchers", "code_index_rules_file", str),
    "AGENTIC_RAG_TERMS_FILE": ("watchers", "agentic_terms_file", str),
}


def _default_config_path() -> Path:
    return Path(__file__).resolve().parents[3] / "config.yaml"


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        value = yaml.safe_load(handle) or {}
    if not isinstance(value, dict):
        raise ValueError(f"RAG configuration must be a mapping: {path}")
    return value


def _coerce_bool(value: Any, name: str) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")


def _section(data: Mapping[str, Any], name: str) -> dict[str, Any]:
    value = data.get(name, {})
    if not isinstance(value, dict):
        raise ValueError(f"Configuration section '{name}' must be a mapping")
    return dict(value)


def _merge(base: dict[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(result.get(key), Mapping):
            result[key] = _merge(dict(result[key]), value)
        else:
            result[key] = value
    return result


def _apply_environment(data: dict[str, Any], environ: Mapping[str, str]) -> None:
    for env_name, (section, key, converter) in ENV_OVERRIDES.items():
        raw = environ.get(env_name)
        if raw is None or raw == "":
            continue
        try:
            value = converter(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{env_name} has an invalid value: {raw!r}") from exc
        data.setdefault(section, {})[key] = value

    boolean_env = {
        "ENABLE_AGENTIC_RETRIEVAL": ("agentic", "enabled"),
        "AGENTIC_RAG_LOGS": ("logging", "enabled"),
    }
    for env_name, (section, key) in boolean_env.items():
        if env_name in environ:
            data.setdefault(section, {})[key] = _coerce_bool(environ[env_name], env_name)

    # QDRANT_COLLECTION is service-specific. Callers can choose the matching
    # collection while retaining this long-standing environment variable.


def load_settings(
    config_path: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> Settings:
    """Load settings without initializing model or database clients."""

    env = os.environ if environ is None else environ
    default_path = _default_config_path()
    selected = config_path or env.get("AI_STACK_CONFIG_FILE")
    data = _read_yaml(default_path)
    if selected and Path(selected).resolve() != default_path.resolve():
        data = _merge(data, _read_yaml(Path(selected)))
    _apply_environment(data, env)

    settings = Settings(
        ingestion=IngestionSettings(**_section(data, "ingestion")),
        chunking=ChunkingSettings(**_section(data, "chunking")),
        embeddings=EmbeddingSettings(**_section(data, "embeddings")),
        vector_db=VectorDBSettings(**_section(data, "vector_db")),
        retrieval=RetrievalSettings(**_section(data, "retrieval")),
        llm=LLMSettings(**_section(data, "llm")),
        agentic=AgenticSettings(**_section(data, "agentic")),
        logging=LoggingSettings(**_section(data, "logging")),
        watchers=WatcherSettings(**_section(data, "watchers")),
    )
    _validate(settings)
    return settings


def _validate(settings: Settings) -> None:
    positive = {
        "chunking.memory_size": settings.chunking.memory_size,
        "chunking.code_max_chars": settings.chunking.code_max_chars,
        "vector_db.port": settings.vector_db.port,
        "retrieval.simple_top_k": settings.retrieval.simple_top_k,
        "llm.timeout_seconds": settings.llm.timeout_seconds,
        "agentic.max_steps": settings.agentic.max_steps,
    }
    invalid = [name for name, value in positive.items() if value < 1]
    if invalid:
        raise ValueError("Configuration values must be positive: " + ", ".join(invalid))
    if settings.chunking.code_overlap_chars < 0:
        raise ValueError("chunking.code_overlap_chars cannot be negative")
    if settings.chunking.code_overlap_chars >= settings.chunking.code_max_chars:
        raise ValueError("chunking.code_overlap_chars must be smaller than code_max_chars")
    if not 0 <= settings.agentic.min_confidence <= 1:
        raise ValueError("agentic.min_confidence must be between 0 and 1")
    if settings.embeddings.device not in {"cpu", "cuda"}:
        raise ValueError("embeddings.device must be 'cpu' or 'cuda'")


def load_legacy_json(path: str | Path) -> dict[str, Any]:
    """Read legacy structured rules retained for backward compatibility."""

    selected = Path(path)
    with selected.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Legacy configuration must be an object: {selected}")
    return value
