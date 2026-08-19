"""Agentic RAG FastAPI application."""

import hashlib
import json
import os
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue
from ai_stack_rag.embeddings.provider import EmbeddingProvider

from ai_stack_rag.llm.openai_compat import proxy_completion, upstream_payload
from ai_stack_rag.llm.client import OpenAICompatibleClient
from ai_stack_rag.prompts.utility import classify_utility_prompt
from ai_stack_rag.utils.document_refs import extract_document_filename
from ai_stack_rag.utils.json_log import append_json_event
from ai_stack_rag.utils.legacy_config import default_config_path, load_json_object, require_string_sets
from ai_stack_rag.utils.security import install_security_middleware, validate_proxy_environment
from ai_stack_rag.utils.source_locations import (
    canonical_source_path,
    clean_source_markers,
    format_source_location,
)
from ai_stack_rag.utils.config import load_settings

SETTINGS = load_settings()

SourceName = Literal["code", "memory"]

def env_bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: str, minimum: int = 1) -> int:
    try:
        value = int(os.getenv(name, default))
    except ValueError:
        return int(default)
    return max(value, minimum)


def env_float(name: str, default: str) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return float(default)


QDRANT_HOST = os.getenv("QDRANT_HOST", SETTINGS.vector_db.host)
QDRANT_PORT = env_int("QDRANT_PORT", str(SETTINGS.vector_db.port))
MEMORY_COLLECTION = os.getenv("MEMORY_COLLECTION", SETTINGS.vector_db.memory_collection)
CODE_COLLECTION = os.getenv("CODE_COLLECTION", SETTINGS.vector_db.code_collection)

LLM_BASE_URL = os.getenv("LLM_BASE_URL", SETTINGS.llm.base_url).rstrip("/")
LLM_MODEL = os.getenv("LLM_MODEL", SETTINGS.llm.model)

ENABLE_INDEX_V2 = env_bool("ENABLE_INDEX_V2", "true")
ENABLE_AGENTIC_RETRIEVAL = env_bool("ENABLE_AGENTIC_RETRIEVAL", str(SETTINGS.agentic.enabled))
SKIP_UTILITY_PROMPTS = env_bool("SKIP_UTILITY_PROMPTS", "true")
AGENTIC_MAX_STEPS = env_int("AGENTIC_MAX_STEPS", str(SETTINGS.agentic.max_steps))
AGENTIC_INITIAL_SUBQUERIES = env_int("AGENTIC_INITIAL_SUBQUERIES", str(SETTINGS.agentic.initial_subqueries))
AGENTIC_FOLLOWUP_TOP_K = env_int("AGENTIC_FOLLOWUP_TOP_K", str(SETTINGS.agentic.followup_top_k))
AGENTIC_MAX_TOTAL_CHUNKS = env_int("AGENTIC_MAX_TOTAL_CHUNKS", str(SETTINGS.agentic.max_total_chunks))
AGENTIC_MIN_CONFIDENCE = env_float("AGENTIC_MIN_CONFIDENCE", str(SETTINGS.agentic.min_confidence))
AGENTIC_TOP_K_PER_QUERY = env_int("AGENTIC_TOP_K_PER_QUERY", str(SETTINGS.agentic.top_k_per_query))

EMBED_MODEL_NAME = os.getenv("EMBED_MODEL_NAME", SETTINGS.embeddings.model)
SIMPLE_TOP_K = env_int("SIMPLE_TOP_K", str(SETTINGS.retrieval.simple_top_k))
SCORE_THRESHOLD = env_float("AGENTIC_SCORE_THRESHOLD", str(SETTINGS.retrieval.score_threshold))
MAX_CHUNK_CHARS = env_int("MAX_CHUNK_CHARS", str(SETTINGS.retrieval.max_chunk_chars))
MAX_CONTEXT_CHARS = env_int("MAX_CONTEXT_CHARS", str(SETTINGS.retrieval.max_context_chars))
LOG_FILE = Path(os.getenv("AGENTIC_RAG_LOG_FILE", SETTINGS.logging.agentic_file))
ENABLE_LOGGING = env_bool("AGENTIC_RAG_LOGS", str(SETTINGS.logging.enabled))
TERMS_CONFIG_FILE = default_config_path(
    "AGENTIC_RAG_TERMS_FILE",
    "agentic_rag_terms.json",
    __file__,
)

TERMS_CONFIG_KEYS = [
    "stop_words",
    "implementation_intent_terms",
    "doc_intent_terms",
    "explicit_memory_terms",
    "heuristic_code_terms",
    "heuristic_memory_terms",
]


def load_terms_config(path: Path) -> Dict[str, set[str]]:
    return require_string_sets(
        load_json_object(path, "Agentic RAG terms"),
        TERMS_CONFIG_KEYS,
        "Agentic RAG terms",
        lowercase=True,
    )


TERMS_CONFIG = load_terms_config(TERMS_CONFIG_FILE)

validate_proxy_environment(
    "agentic-rag",
    required_vars=[
        "LLM_BASE_URL",
        "LLM_MODEL",
        "QDRANT_HOST",
        "QDRANT_PORT",
        "MEMORY_COLLECTION",
        "CODE_COLLECTION",
    ],
)

app = FastAPI(title="Agentic RAG API")
install_security_middleware(app, "agentic-rag")


def create_app() -> FastAPI:
    """Return the configured agentic API application."""
    return app

client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
embedder = EmbeddingProvider(EMBED_MODEL_NAME)
llm_client = OpenAICompatibleClient(LLM_BASE_URL, LLM_MODEL, timeout=300)


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: Optional[str] = "agentic-rag"
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.2
    max_tokens: Optional[int] = 2048
    stream: Optional[bool] = False


class AskRequest(BaseModel):
    question: str


class SearchRequest(BaseModel):
    query: str
    source: Optional[Literal["code", "memory", "both"]] = "both"
    top_k: Optional[int] = None


def log_event(event: str, data: Dict[str, Any]) -> None:
    if not ENABLE_LOGGING:
        return
    error = append_json_event(
        LOG_FILE,
        {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "event": event,
            "data": data,
        },
    )
    if error:
        print(f"agentic-rag logging failed: {error}", file=sys.stderr)


log_event("proxy_started", {"service": "agentic-rag"})


def latest_user_message(messages: List[ChatMessage]) -> str:
    for message in reversed(messages):
        if message.role == "user":
            return message.content
    return ""


def extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    text = text.strip()
    if not text:
        return None
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def call_llm_messages(
    messages: List[Dict[str, str]],
    temperature: float = 0.2,
    max_tokens: int = 2048,
) -> str:
    return llm_client.chat(
        messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def call_llm_json(prompt: str, fallback: Dict[str, Any], max_tokens: int = 1024) -> Dict[str, Any]:
    try:
        text = call_llm_messages(
            [
                {
                    "role": "system",
                    "content": "Return valid JSON only. Do not include markdown fences.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=max_tokens,
        )
        return extract_json_object(text) or fallback
    except Exception as exc:
        log_event("llm_json_error", {"error": str(exc), "fallback": fallback})
        return fallback


def has_config_term(text: str, terms: set[str]) -> bool:
    normalized = text.lower()
    tokens = set(re.findall(r"[a-z0-9_]+", normalized))
    for term in terms:
        if " " in term:
            if term in normalized:
                return True
            continue
        if term in tokens:
            return True
    return False


def heuristic_sources(question: str) -> List[SourceName]:
    q = question.lower()
    code_terms = TERMS_CONFIG["heuristic_code_terms"] | TERMS_CONFIG["implementation_intent_terms"]
    memory_terms = (
        TERMS_CONFIG["heuristic_memory_terms"]
        | TERMS_CONFIG["doc_intent_terms"]
        | TERMS_CONFIG["explicit_memory_terms"]
    )
    wants_code = has_config_term(q, code_terms)
    wants_memory = has_config_term(q, memory_terms)
    if wants_code and not wants_memory:
        return ["code"]
    if wants_memory and not wants_code:
        return ["memory"]
    return ["code", "memory"]


def is_exhaustive_question(question: str) -> bool:
    normalized = question.lower()
    return bool(re.search(r"\b(all|every)\b|\bcomplete list\b|\bcurrently available\b", normalized))


def fallback_analysis(question: str) -> Dict[str, Any]:
    words = question.split()
    is_complex = len(words) > 18 or any(token in question.lower() for token in ["compare", "how", "why", "and", "across"])
    sources = heuristic_sources(question)
    return {
        "question_type": "multi_hop" if is_complex else "simple",
        "complexity": "high" if is_complex else "low",
        "needs_multiple_sources": is_complex or len(sources) > 1,
        "main_topics": words[:8],
        "expected_evidence": ["implementation details", "documentation notes"],
        "sources": sources,
        "exhaustive": is_exhaustive_question(question),
    }


def analyze_question(question: str) -> Dict[str, Any]:
    fallback = fallback_analysis(question)
    if not ENABLE_AGENTIC_RETRIEVAL:
        return fallback
    prompt = f"""
Analyze this RAG question and return JSON only.

Question:
{question}

Return:
{{
  "question_type": "simple | multi_hop | code | memory | mixed",
  "complexity": "low | medium | high",
  "needs_multiple_sources": true,
  "main_topics": ["..."],
  "expected_evidence": ["..."],
  "sources": ["code", "memory"]
}}
"""
    data = call_llm_json(prompt, fallback)
    sources = data.get("sources")
    if not isinstance(sources, list) or not sources:
        data["sources"] = fallback["sources"]
    data["sources"] = [source for source in data["sources"] if source in {"code", "memory"}] or fallback["sources"]
    for required_source in fallback["sources"]:
        if required_source not in data["sources"]:
            data["sources"].append(required_source)
    return data


def fallback_plan(question: str, analysis: Dict[str, Any]) -> List[Dict[str, str]]:
    sources = analysis.get("sources") or heuristic_sources(question)
    count = 1 if analysis.get("complexity") == "low" else AGENTIC_INITIAL_SUBQUERIES
    topics = analysis.get("main_topics") if isinstance(analysis.get("main_topics"), list) else []
    topic_text = " ".join(str(topic) for topic in topics[:5]).strip()
    queries = [question]
    if topic_text and topic_text.lower() not in question.lower():
        queries.append(f"{question} {topic_text}")
    queries.extend(
        [
            f"{question} implementation configuration",
            f"{question} docs README architecture",
        ]
    )
    plan: List[Dict[str, str]] = []
    for index in range(count):
        source = sources[index % len(sources)]
        plan.append(
            {
                "sub_question": question if index == 0 else f"Find evidence for: {question}",
                "query": queries[index % len(queries)],
                "source": source,
            }
        )
    return plan


def build_retrieval_plan(question: str, analysis: Dict[str, Any]) -> List[Dict[str, str]]:
    fallback = {"plan": fallback_plan(question, analysis)}
    if not ENABLE_AGENTIC_RETRIEVAL:
        return fallback["plan"]
    prompt = f"""
Create a retrieval plan for this RAG question.

Question:
{question}

Question analysis:
{json.dumps(analysis, ensure_ascii=False)}

Return JSON only:
{{
  "plan": [
    {{
      "sub_question": "specific evidence need",
      "query": "short search query",
      "source": "code | memory"
    }}
  ]
}}

Use at most {AGENTIC_INITIAL_SUBQUERIES} planned queries.
"""
    data = call_llm_json(prompt, fallback)
    raw_plan = data.get("plan") if isinstance(data.get("plan"), list) else fallback["plan"]
    plan = []
    for item in raw_plan[:AGENTIC_INITIAL_SUBQUERIES]:
        if not isinstance(item, dict):
            continue
        source = item.get("source")
        if source not in {"code", "memory"}:
            source = (analysis.get("sources") or ["code", "memory"])[0]
        query = str(item.get("query") or question).strip()
        plan.append(
            {
                "sub_question": str(item.get("sub_question") or query).strip(),
                "query": query,
                "source": source,
            }
        )
    plan = plan or fallback["plan"]
    if "memory" in heuristic_sources(question) and not any(item["source"] == "memory" for item in plan):
        memory_query = {"sub_question": question, "query": question, "source": "memory"}
        if len(plan) >= AGENTIC_INITIAL_SUBQUERIES:
            plan[-1] = memory_query
        else:
            plan.append(memory_query)
    return plan


def collection_for_source(source: SourceName) -> str:
    return CODE_COLLECTION if source == "code" else MEMORY_COLLECTION


def point_to_chunk(point: Any, source: SourceName, query: str) -> Dict[str, Any]:
    payload = point.payload or {}
    text = str(payload.get("text") or "")
    file_path = (
        payload.get("relative_path")
        or payload.get("file_path")
        or payload.get("file")
        or payload.get("path")
        or "unknown"
    )
    repo_name = payload.get("repo") or payload.get("repo_name")
    chunk_index = payload.get("chunk_index", payload.get("symbol_subchunk_index", 0))
    source_path = canonical_source_path(
        source,
        repo_name=repo_name,
        relative_path=payload.get("relative_path"),
        file_path=file_path,
        source_path=payload.get("source_path"),
    )
    raw_id = payload.get("chunk_id") or f"{source}:{repo_name or ''}:{file_path}:{chunk_index}"
    content_hash = payload.get("content_hash") or hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return {
        "chunk_id": str(raw_id),
        "source_type": source,
        "repo_name": repo_name,
        "file_path": str(file_path),
        "source_path": source_path,
        "chunk_index": chunk_index,
        "line_start": payload.get("line_start"),
        "line_end": payload.get("line_end"),
        "content_hash": content_hash,
        "score": float(getattr(point, "score", 1.0) or 0),
        "query": query,
        "language": payload.get("language"),
        "category": payload.get("category"),
        "symbol_type": payload.get("symbol_type"),
        "symbol_name": payload.get("symbol_name"),
        "text": text[:MAX_CHUNK_CHARS],
    }


def search_source(query: str, source: SourceName, top_k: int) -> List[Dict[str, Any]]:
    try:
        vector = embedder.encode(query)
        results = client.query_points(
            collection_name=collection_for_source(source),
            query=vector,
            limit=max(top_k * 4, top_k),
            with_payload=True,
            with_vectors=False,
        )
    except Exception as exc:
        log_event("search_error", {"query": query, "source": source, "error": str(exc)})
        return []

    chunks = []
    for point in results.points:
        if float(point.score or 0) < SCORE_THRESHOLD:
            continue
        chunks.append(point_to_chunk(point, source, query))
        if len(chunks) >= top_k:
            break
    return chunks


def exact_memory_document(filename: str) -> List[Dict[str, Any]]:
    normalized = Path(filename).name.lower()
    records: List[Any] = []
    try:
        records, _ = client.scroll(
            collection_name=MEMORY_COLLECTION,
            scroll_filter=Filter(
                must=[FieldCondition(key="file_name", match=MatchValue(value=normalized))]
            ),
            limit=AGENTIC_MAX_TOTAL_CHUNKS * 8,
            with_payload=True,
            with_vectors=False,
        )
    except Exception as exc:
        log_event("exact_document_index_lookup_error", {"filename": normalized, "error": str(exc)})

    # Existing points do not have file_name until memory is reindexed.
    if not records:
        offset = None
        try:
            while True:
                page, offset = client.scroll(
                    collection_name=MEMORY_COLLECTION,
                    limit=256,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                )
                records.extend(
                    record
                    for record in page
                    if Path(str((record.payload or {}).get("file") or "")).name.lower() == normalized
                )
                if offset is None:
                    break
        except Exception as exc:
            log_event("exact_document_legacy_scan_error", {"filename": normalized, "error": str(exc)})

    chunks = [point_to_chunk(record, "memory", filename) for record in records]
    chunks.sort(key=lambda item: (item.get("file_path") or "", int(item.get("chunk_index") or 0)))
    selected: List[Dict[str, Any]] = []
    context_chars = 0
    for chunk in chunks:
        text_length = len(chunk.get("text") or "")
        if selected and context_chars + text_length > MAX_CONTEXT_CHARS:
            break
        selected.append(chunk)
        context_chars += text_length
    log_event(
        "exact_document_lookup",
        {
            "filename": normalized,
            "collection": MEMORY_COLLECTION,
            "matched_paths": sorted({chunk["file_path"] for chunk in chunks}),
            "matched_chunks": len(chunks),
            "selected_chunks": len(selected),
            "context_chars": context_chars,
        },
    )
    return selected


def dedupe_chunks(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    unique = []
    for chunk in sorted(chunks, key=lambda item: item.get("score") or 0, reverse=True):
        keys = [
            chunk.get("chunk_id"),
            f"{chunk.get('file_path')}:{chunk.get('chunk_index')}",
            chunk.get("content_hash"),
        ]
        if any(key in seen for key in keys if key):
            continue
        for key in keys:
            if key:
                seen.add(key)
        unique.append(chunk)
    return unique[:AGENTIC_MAX_TOTAL_CHUNKS]


def format_citation(chunk: Dict[str, Any]) -> str:
    return format_source_location(
        str(chunk.get("source_type") or "code"),
        repo_name=chunk.get("repo_name"),
        file_path=chunk.get("file_path"),
        source_path=chunk.get("source_path"),
        line_start=chunk.get("line_start"),
        line_end=chunk.get("line_end"),
        chunk_index=chunk.get("chunk_index"),
    )


def format_evidence(chunks: List[Dict[str, Any]]) -> str:
    parts = []
    total_chars = 0
    for index, chunk in enumerate(chunks, start=1):
        text = chunk.get("text") or ""
        block = f"""
[EVIDENCE {index}]
Location: {format_citation(chunk)}
Source type: {chunk.get("source_type")}
Score: {round(float(chunk.get("score") or 0), 4)}
Category: {chunk.get("category")}
Symbol: {chunk.get("symbol_type")} {chunk.get("symbol_name")}

{text}
[/EVIDENCE {index}]
""".strip()
        if total_chars + len(block) > MAX_CONTEXT_CHARS:
            break
        parts.append(block)
        total_chars += len(block)
    return "\n\n".join(parts) if parts else "No indexed evidence was found."


def tokenize_for_relevance(text: str) -> set[str]:
    stop_words = TERMS_CONFIG["stop_words"]
    return {
        token
        for token in re.findall(r"[a-z0-9_]+", text.lower())
        if len(token) > 2 and token not in stop_words
    }


def chunk_relevance_score(question_tokens: set[str], chunk: Dict[str, Any]) -> float:
    text_tokens = tokenize_for_relevance(
        " ".join(
            str(value or "")
            for value in [
                chunk.get("file_path"),
                chunk.get("symbol_name"),
                chunk.get("category"),
                chunk.get("language"),
                chunk.get("text"),
            ]
        )
    )
    overlap = len(question_tokens & text_tokens)
    lexical_score = overlap / max(len(question_tokens), 1)
    retrieval_score = float(chunk.get("score") or 0.0)
    symbol_bonus = 0.05 if chunk.get("symbol_name") else 0.0
    return retrieval_score + lexical_score + symbol_bonus


def select_answer_chunks(question: str, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not chunks:
        return []

    question_tokens = tokenize_for_relevance(question)
    ranked = sorted(
        chunks,
        key=lambda chunk: chunk_relevance_score(question_tokens, chunk),
        reverse=True,
    )
    answer_limit = max(1, min(AGENTIC_MAX_TOTAL_CHUNKS, 8))

    selected: List[Dict[str, Any]] = []
    selected_ids: set[str] = set()
    present_sources = {chunk.get("source_type") for chunk in ranked}
    target_sources: List[SourceName] = [
        source for source in ("code", "memory") if source in present_sources
    ]

    for source in target_sources:
        source_chunk = next(
            (chunk for chunk in ranked if chunk.get("source_type") == source),
            None,
        )
        if source_chunk:
            chunk_id = str(source_chunk.get("chunk_id") or id(source_chunk))
            selected.append(source_chunk)
            selected_ids.add(chunk_id)

    for chunk in ranked:
        if len(selected) >= answer_limit:
            break
        chunk_id = str(chunk.get("chunk_id") or id(chunk))
        if chunk_id in selected_ids:
            continue
        selected.append(chunk)
        selected_ids.add(chunk_id)

    return selected


def calculate_evidence_confidence(question: str, chunks: List[Dict[str, Any]]) -> Dict[str, float]:
    if not chunks:
        return {
            "count_score": 0.0,
            "retrieval_score": 0.0,
            "coverage_score": 0.0,
            "deterministic_confidence": 0.0,
        }

    count_score = min(len(chunks) / 8.0, 1.0)
    top_scores = sorted(
        (max(0.0, min(1.0, float(chunk.get("score") or 0.0))) for chunk in chunks),
        reverse=True,
    )[:5]
    retrieval_score = sum(top_scores) / len(top_scores)

    question_tokens = tokenize_for_relevance(question)
    evidence_tokens: set[str] = set()
    for chunk in chunks:
        evidence_tokens.update(
            tokenize_for_relevance(
                " ".join(
                    str(value or "")
                    for value in [
                        chunk.get("repo_name"),
                        chunk.get("file_path"),
                        chunk.get("symbol_name"),
                        chunk.get("category"),
                        chunk.get("language"),
                        chunk.get("text"),
                    ]
                )
            )
        )
    coverage_score = (
        len(question_tokens & evidence_tokens) / len(question_tokens)
        if question_tokens else 0.0
    )
    deterministic_confidence = (
        (0.25 * count_score) +
        (0.35 * retrieval_score) +
        (0.40 * coverage_score)
    )
    return {
        "count_score": round(count_score, 4),
        "retrieval_score": round(retrieval_score, 4),
        "coverage_score": round(coverage_score, 4),
        "deterministic_confidence": round(deterministic_confidence, 4),
    }


def evaluate_evidence(question: str, chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not ENABLE_AGENTIC_RETRIEVAL:
        confidence = 0.75 if chunks else 0.0
        return {
            "enough": bool(chunks),
            "confidence": confidence,
            "missing_information": [] if chunks else ["No relevant chunks found"],
            "followup_queries": [],
            "confidence_components": {
                "deterministic_confidence": confidence,
                "evaluator_confidence": None,
                "evaluator_valid": False,
                "final_confidence": confidence,
            },
        }
    confidence_components = calculate_evidence_confidence(question, chunks)
    fallback_confidence = confidence_components["deterministic_confidence"]
    fallback = {
        "enough": fallback_confidence >= AGENTIC_MIN_CONFIDENCE,
        "confidence": fallback_confidence,
        "missing_information": [] if chunks else ["No relevant chunks found"],
        "followup_queries": [],
    }
    prompt = f"""
You are an evidence evaluator for a RAG system.

User question:
{question}

Evidence gathered:
{format_evidence(chunks)}

Decide whether the evidence is enough to answer.

Return JSON only:
{{
  "enough": true,
  "confidence": 0.75,
  "missing_information": [],
  "followup_queries": []
}}

Use 0.0 confidence only when there is no relevant evidence. Judge coverage of the
specific evidence requested, not merely the number of chunks.
Use at most {AGENTIC_FOLLOWUP_TOP_K} follow-up queries.
"""
    data = call_llm_json(prompt, fallback)
    raw_confidence = data.get("confidence", fallback["confidence"])
    evaluator_valid = True
    try:
        evaluator_confidence = float(raw_confidence)
    except (TypeError, ValueError):
        evaluator_confidence = fallback["confidence"]
        evaluator_valid = False
    evaluator_confidence = max(0.0, min(1.0, evaluator_confidence))
    if chunks and evaluator_confidence == 0.0:
        evaluator_valid = False

    deterministic_confidence = confidence_components["deterministic_confidence"]
    if evaluator_valid:
        final_confidence = (0.60 * deterministic_confidence) + (0.40 * evaluator_confidence)
    else:
        final_confidence = deterministic_confidence
    final_confidence = round(max(0.0, min(1.0, final_confidence)), 4)

    evaluator_enough = bool(data.get("enough"))
    data["confidence"] = final_confidence
    data["enough"] = final_confidence >= AGENTIC_MIN_CONFIDENCE and (
        evaluator_enough or deterministic_confidence >= AGENTIC_MIN_CONFIDENCE
    )
    data["confidence_components"] = {
        **confidence_components,
        "evaluator_confidence": round(evaluator_confidence, 4),
        "evaluator_valid": evaluator_valid,
        "final_confidence": final_confidence,
    }
    if not isinstance(data.get("followup_queries"), list):
        data["followup_queries"] = []
    if not isinstance(data.get("missing_information"), list):
        data["missing_information"] = []
    return data


def run_simple_retrieval(question: str) -> Dict[str, Any]:
    plan = [
        {"sub_question": question, "query": question, "source": source}
        for source in heuristic_sources(question)
    ]
    chunks: List[Dict[str, Any]] = []
    for item in plan:
        chunks.extend(search_source(item["query"], item["source"], SIMPLE_TOP_K))
    chunks = dedupe_chunks(chunks)
    evaluation = evaluate_evidence(question, chunks)
    return {
        "analysis": fallback_analysis(question),
        "plan": plan,
        "queries_used": plan,
        "chunks": chunks,
        "evaluations": [evaluation],
        "confidence": evaluation["confidence"],
        "stop_reason": "simple_retrieval",
    }


def run_agentic_retrieval(question: str) -> Dict[str, Any]:
    filename = extract_document_filename(question)
    if filename:
        started = time.monotonic()
        chunks = exact_memory_document(filename)
        if chunks:
            elapsed_ms = round((time.monotonic() - started) * 1000, 2)
            return {
                "analysis": {**fallback_analysis(question), "resolved_filename": filename},
                "plan": [{"sub_question": question, "query": filename, "source": "memory"}],
                "queries_used": [{"step": "1", "query": filename, "source": "memory"}],
                "chunks": chunks,
                "evaluations": [],
                "confidence": 1.0,
                "confidence_components": {"exact_filename_match": 1.0},
                "stop_reason": "exact_document_match",
                "retrieval_mode": "exact_document",
                "elapsed_ms": elapsed_ms,
            }
        log_event(
            "exact_document_fallback",
            {"filename": filename, "collection": MEMORY_COLLECTION, "retrieval_mode": "semantic"},
        )
    if not ENABLE_INDEX_V2 or not ENABLE_AGENTIC_RETRIEVAL:
        return run_simple_retrieval(question)

    analysis = analyze_question(question)
    plan = build_retrieval_plan(question, analysis)
    all_chunks: List[Dict[str, Any]] = []
    queries_used: List[Dict[str, str]] = []
    evaluations: List[Dict[str, Any]] = []
    stop_reason = "max_steps"
    executed_queries: set[str] = set()
    retrieval_started = time.monotonic()

    current_plan = plan
    for step in range(1, AGENTIC_MAX_STEPS + 1):
        step_started = time.monotonic()
        step_chunks = []
        for item in current_plan:
            source = item.get("source")
            query = item.get("query") or question
            if source not in {"code", "memory"}:
                continue
            query_key = f"{source}:{' '.join(str(query).lower().split())}"
            if query_key in executed_queries:
                continue
            executed_queries.add(query_key)
            query_record = {
                "step": str(step),
                "sub_question": item.get("sub_question", query),
                "query": query,
                "source": source,
            }
            queries_used.append(query_record)
            if step == 1 and is_exhaustive_question(question):
                top_k = min(AGENTIC_MAX_TOTAL_CHUNKS, max(8, AGENTIC_TOP_K_PER_QUERY))
            else:
                top_k = AGENTIC_TOP_K_PER_QUERY if step == 1 else AGENTIC_FOLLOWUP_TOP_K
            step_chunks.extend(search_source(query, source, top_k))

        before_count = len(all_chunks)
        all_chunks = dedupe_chunks(all_chunks + step_chunks)
        new_chunk_count = len(all_chunks) - before_count
        evaluation = evaluate_evidence(question, all_chunks)
        evaluations.append(evaluation)
        components = evaluation.get("confidence_components", {})

        log_event(
            "retrieval_step",
            {
                "question": question,
                "step": step,
                "planned_queries": len(current_plan),
                "new_chunks": new_chunk_count,
                "total_chunks": len(all_chunks),
                "confidence": evaluation["confidence"],
                "enough": evaluation["enough"],
                "confidence_components": components,
                "query_sources": sorted({item["source"] for item in queries_used if item["step"] == str(step)}),
                "top_score": max((float(chunk.get("score") or 0.0) for chunk in all_chunks), default=0.0),
                "elapsed_ms": round((time.monotonic() - step_started) * 1000, 2),
            },
        )

        if evaluation["enough"]:
            stop_reason = "enough_evidence"
            break
        if len(all_chunks) >= AGENTIC_MAX_TOTAL_CHUNKS:
            stop_reason = "max_total_chunks"
            break
        if new_chunk_count == 0:
            stop_reason = "no_new_chunks"
            break

        followups = [str(query).strip() for query in evaluation.get("followup_queries", []) if str(query).strip()]
        if not followups and is_exhaustive_question(question):
            followups = [f"{question} complete list definitions aliases functions commands"]
        if not followups:
            stop_reason = "no_followup_queries"
            break
        sources = analysis.get("sources") or ["code", "memory"]
        current_plan = [
            {
                "sub_question": f"Follow-up evidence for: {query}",
                "query": query,
                "source": sources[index % len(sources)],
            }
            for index, query in enumerate(followups[:AGENTIC_FOLLOWUP_TOP_K])
        ]

    final_evaluation = evaluations[-1] if evaluations else {"confidence": 0.0}
    total_elapsed_ms = round((time.monotonic() - retrieval_started) * 1000, 2)
    log_event(
        "retrieval_complete",
        {
            "question_hash": hashlib.sha256(question.encode("utf-8")).hexdigest()[:12],
            "steps": len(evaluations),
            "queries_used": len(queries_used),
            "total_chunks": len(all_chunks),
            "confidence": final_evaluation.get("confidence", 0.0),
            "confidence_components": final_evaluation.get("confidence_components", {}),
            "stop_reason": stop_reason,
            "elapsed_ms": total_elapsed_ms,
        },
    )
    return {
        "analysis": analysis,
        "plan": plan,
        "queries_used": queries_used,
        "chunks": all_chunks,
        "evaluations": evaluations,
        "confidence": final_evaluation.get("confidence", 0.0),
        "confidence_components": final_evaluation.get("confidence_components", {}),
        "stop_reason": stop_reason,
        "elapsed_ms": total_elapsed_ms,
    }


def build_final_messages(question: str, trace: Dict[str, Any]) -> List[Dict[str, str]]:
    if trace.get("retrieval_mode") == "exact_document":
        chunks = trace.get("chunks", [])
    else:
        chunks = select_answer_chunks(question, trace.get("chunks", []))
    trace["answer_chunks"] = chunks
    citations = [format_citation(chunk) for chunk in chunks]
    prompt = f"""
You are an agentic RAG assistant connected to private code and memory indexes.

Answer the user question using the retrieved evidence. If evidence is incomplete,
say what is uncertain. Refer to evidence inline using the exact Location value.
Never use numbered source labels such as [Source 1] and do not add a numbered
Sources section. Memory locations must remain filenames only.

User question:
{question}

Retrieval confidence:
{trace.get("confidence")}

Stop reason:
{trace.get("stop_reason")}

Evidence:
{format_evidence(chunks)}

Allowed locations:
{json.dumps(citations, ensure_ascii=False)}
"""
    return [
        {"role": "system", "content": "You answer with grounded citations and do not invent evidence."},
        {"role": "user", "content": prompt},
    ]


def build_final_answer(question: str, trace: Dict[str, Any], temperature: float, max_tokens: int) -> str:
    messages = build_final_messages(question, trace)
    chunks = trace.get("answer_chunks", [])
    try:
        answer = call_llm_messages(messages, temperature=temperature, max_tokens=max_tokens)
        return clean_source_markers(answer, [format_citation(chunk) for chunk in chunks])
    except Exception as exc:
        log_event("final_answer_error", {"error": str(exc)})
        if not chunks:
            return f"I could not find indexed evidence for this question. Model call failed: {exc}"
        sources = "\n".join(f"- {format_citation(chunk)}" for chunk in chunks)
        return (
            "I found relevant indexed evidence, but the final model call failed. "
            f"Error: {exc}\n\nFiles:\n{sources}"
        )


def answer_question(question: str, temperature: float = 0.2, max_tokens: int = 2048) -> Dict[str, Any]:
    trace = run_agentic_retrieval(question)
    answer = build_final_answer(question, trace, temperature, max_tokens)
    return {
        "question": question,
        "answer": answer,
        "trace": trace,
        "sources": [format_citation(chunk) for chunk in trace.get("chunks", [])],
    }


@app.get("/", response_class=HTMLResponse)
def index_page():
    return """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Agentic RAG</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 0; background: #101418; color: #edf2f7; }
    main { max-width: 980px; margin: 0 auto; padding: 32px 20px; }
    textarea, button { font: inherit; }
    textarea { width: 100%; min-height: 130px; box-sizing: border-box; border: 1px solid #344150; border-radius: 6px; padding: 12px; color: #edf2f7; background: #151b22; }
    button { margin-top: 12px; border: 0; border-radius: 6px; padding: 10px 14px; color: #061018; background: #7dd3fc; cursor: pointer; }
    pre { white-space: pre-wrap; background: #151b22; border: 1px solid #344150; border-radius: 6px; padding: 14px; overflow: auto; }
    .meta { color: #9fb0c3; }
  </style>
</head>
<body>
  <main>
    <h1>Agentic RAG</h1>
    <p class="meta">OpenAI-compatible connector: <code>/v1</code>. Debug endpoint: <code>/v1/rag/debug</code>.</p>
    <textarea id="question" placeholder="Ask a memory, code, or mixed question"></textarea>
    <button onclick="ask()">Ask</button>
    <h2>Result</h2>
    <pre id="result">Ready.</pre>
  </main>
  <script>
    async function ask() {
      const result = document.getElementById('result');
      result.textContent = 'Thinking...';
      const question = document.getElementById('question').value;
      const res = await fetch('/ask', {
        method: 'POST',
        headers: {'content-type': 'application/json'},
        body: JSON.stringify({question})
      });
      result.textContent = JSON.stringify(await res.json(), null, 2);
    }
  </script>
</body>
</html>
"""


@app.get("/v1/models")
def models():
    return {
        "object": "list",
        "data": [
            {
                "id": "agentic-rag",
                "object": "model",
                "owned_by": "local",
            }
        ],
    }


@app.post("/search")
def search(req: SearchRequest):
    sources: List[SourceName]
    if req.source == "code":
        sources = ["code"]
    elif req.source == "memory":
        sources = ["memory"]
    else:
        sources = ["code", "memory"]
    chunks: List[Dict[str, Any]] = []
    for source in sources:
        chunks.extend(search_source(req.query, source, req.top_k or SIMPLE_TOP_K))
    return {"query": req.query, "results": dedupe_chunks(chunks)}


@app.post("/ask")
def ask(req: AskRequest):
    return answer_question(req.question)


@app.post("/v1/rag/debug")
def rag_debug(req: AskRequest):
    return run_agentic_retrieval(req.question)


@app.post("/v1/chat/completions")
def chat_completions(req: ChatCompletionRequest):
    user_question = latest_user_message(req.messages)
    if not user_question:
        return {"error": "No user message found"}

    utility_prompt_type = classify_utility_prompt(user_question) if SKIP_UTILITY_PROMPTS else None
    if utility_prompt_type:
        log_event(
            "utility_prompt_skipped",
            {
                "utility_prompt_type": utility_prompt_type,
                "question_hash": hashlib.sha256(user_question.encode("utf-8")).hexdigest()[:12],
            },
        )
        payload = upstream_payload(
            LLM_MODEL,
            [{"role": message.role, "content": message.content} for message in req.messages],
            req.temperature or 0.2,
            req.max_tokens or 2048,
            bool(req.stream),
        )
        return proxy_completion(
            f"{LLM_BASE_URL}/chat/completions",
            payload,
            "agentic-rag",
            "agentic-rag-utility",
            bool(req.stream),
        )

    if req.stream:
        trace = run_agentic_retrieval(user_question)
        payload = upstream_payload(
            LLM_MODEL,
            build_final_messages(user_question, trace),
            req.temperature or 0.2,
            req.max_tokens or 2048,
            True,
        )
        return proxy_completion(
            f"{LLM_BASE_URL}/chat/completions",
            payload,
            "agentic-rag",
            "agentic-rag",
            True,
            content_transform=lambda content: clean_source_markers(
                content,
                [format_citation(chunk) for chunk in trace.get("answer_chunks", [])],
            ),
        )

    result = answer_question(
        user_question,
        temperature=req.temperature or 0.2,
        max_tokens=req.max_tokens or 2048,
    )

    return chat_completion_payload(result["answer"])


def chat_completion_payload(content: str) -> Dict[str, Any]:
    return {
        "id": f"agentic-rag-{uuid.uuid4()}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "agentic-rag",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content,
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
    }
