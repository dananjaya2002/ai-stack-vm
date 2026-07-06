import hashlib
import json
import os
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

import requests
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue
from sentence_transformers import SentenceTransformer

sys.path.append(str(Path(__file__).resolve().parents[1]))
from proxy_security import install_security_middleware, validate_proxy_environment


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


QDRANT_HOST = os.getenv("QDRANT_HOST", "qdrant")
QDRANT_PORT = env_int("QDRANT_PORT", "6333")
MEMORY_COLLECTION = os.getenv("MEMORY_COLLECTION", "engineering-memory")
CODE_COLLECTION = os.getenv("CODE_COLLECTION", "code-memory")

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://vm-llama:8082/v1").rstrip("/")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen2.5-coder-7b-instruct-q4_k_m.gguf")

ENABLE_INDEX_V2 = env_bool("ENABLE_INDEX_V2", "true")
ENABLE_AGENTIC_RETRIEVAL = env_bool("ENABLE_AGENTIC_RETRIEVAL", "true")
AGENTIC_MAX_STEPS = env_int("AGENTIC_MAX_STEPS", "4")
AGENTIC_INITIAL_SUBQUERIES = env_int("AGENTIC_INITIAL_SUBQUERIES", "3")
AGENTIC_FOLLOWUP_TOP_K = env_int("AGENTIC_FOLLOWUP_TOP_K", "4")
AGENTIC_MAX_TOTAL_CHUNKS = env_int("AGENTIC_MAX_TOTAL_CHUNKS", "16")
AGENTIC_MIN_CONFIDENCE = env_float("AGENTIC_MIN_CONFIDENCE", "0.70")
AGENTIC_TOP_K_PER_QUERY = env_int("AGENTIC_TOP_K_PER_QUERY", "3")

EMBED_MODEL_NAME = os.getenv("EMBED_MODEL_NAME", "all-MiniLM-L6-v2")
SIMPLE_TOP_K = env_int("SIMPLE_TOP_K", "6")
SCORE_THRESHOLD = env_float("AGENTIC_SCORE_THRESHOLD", "0.35")
MAX_CHUNK_CHARS = env_int("MAX_CHUNK_CHARS", "4000")
MAX_CONTEXT_CHARS = env_int("MAX_CONTEXT_CHARS", "50000")
LOG_FILE = Path(os.getenv("AGENTIC_RAG_LOG_FILE", "/logs/agentic-rag/agentic_rag.log"))
ENABLE_LOGGING = env_bool("AGENTIC_RAG_LOGS", "true")
TERMS_CONFIG_FILE = Path(
    os.getenv(
        "AGENTIC_RAG_TERMS_FILE",
        str(Path(__file__).resolve().with_name("agentic_rag_terms.json")),
    )
)

TERMS_CONFIG_KEYS = [
    "stop_words",
    "implementation_intent_terms",
    "doc_intent_terms",
    "explicit_memory_terms",
    "heuristic_code_terms",
    "heuristic_memory_terms",
]


def normalize_term_list(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {
        str(term).strip().lower()
        for term in value
        if str(term).strip()
    }


def load_terms_config(path: Path) -> Dict[str, set[str]]:
    try:
        raw_config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Unable to load Agentic RAG terms config: {path}") from exc
    if not isinstance(raw_config, dict):
        raise RuntimeError(f"Agentic RAG terms config must be a JSON object: {path}")

    terms_config: Dict[str, set[str]] = {}
    missing_keys = [key for key in TERMS_CONFIG_KEYS if key not in raw_config]
    if missing_keys:
        raise RuntimeError(
            f"Agentic RAG terms config is missing required keys: {', '.join(missing_keys)}"
        )

    for key in TERMS_CONFIG_KEYS:
        terms = normalize_term_list(raw_config.get(key))
        if not terms:
            raise RuntimeError(f"Agentic RAG terms config key must not be empty: {key}")
        terms_config[key] = terms
    return terms_config


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

client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
embedder = SentenceTransformer(EMBED_MODEL_NAME)


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
    repo: Optional[str] = None


def log_event(event: str, data: Dict[str, Any]) -> None:
    if not ENABLE_LOGGING:
        return
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "event": event,
                        "data": data,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    except Exception as exc:
        print(f"agentic-rag logging failed: {exc}", file=sys.stderr)


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
    response = requests.post(
        f"{LLM_BASE_URL}/chat/completions",
        json={
            "model": LLM_MODEL,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        },
        timeout=300,
    )
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"]


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


REPO_TOKEN_RE = re.compile(r"\b[a-zA-Z0-9][a-zA-Z0-9._-]*-[a-zA-Z0-9._-]*\b")
STOP_WORDS = TERMS_CONFIG["stop_words"]
IMPLEMENTATION_INTENT_TERMS = TERMS_CONFIG["implementation_intent_terms"]
DOC_INTENT_TERMS = TERMS_CONFIG["doc_intent_terms"]
EXPLICIT_MEMORY_TERMS = TERMS_CONFIG["explicit_memory_terms"]
HEURISTIC_CODE_TERMS = TERMS_CONFIG["heuristic_code_terms"]
HEURISTIC_MEMORY_TERMS = TERMS_CONFIG["heuristic_memory_terms"]


def normalize_repo_name(value: str) -> str:
    value = value.strip().rstrip("/").split("/")[-1]
    if value.endswith(".git"):
        value = value[:-4]
    return re.sub(r"[^A-Za-z0-9._-]", "", value)


def detect_repo_name(question: str) -> Optional[str]:
    github_match = re.search(r"github\.com/[^/\s]+/([^/\s]+)", question, re.IGNORECASE)
    if github_match:
        repo = normalize_repo_name(github_match.group(1))
        if repo:
            return repo

    lower_question = question.lower()
    tokens = [normalize_repo_name(match.group(0)) for match in REPO_TOKEN_RE.finditer(question)]
    tokens = [token for token in tokens if token and "-" in token]

    for token in tokens:
        lowered = token.lower()
        if lowered in lower_question and any(marker in lowered for marker in {"app", "repo", "iot", "api", "web"}):
            return token

    return tokens[0] if tokens else None


def extract_query_terms(text: str) -> set[str]:
    terms = set()
    for raw in re.findall(r"[A-Za-z][A-Za-z0-9_]{2,}", text.lower()):
        if raw not in STOP_WORDS:
            terms.add(raw)

    for phrase in re.findall(r"[A-Za-z]+(?:[A-Z][a-z0-9]+)+", text):
        terms.add(phrase.lower())

    return terms


def wants_implementation_evidence(question: str) -> bool:
    q = question.lower()
    return any(term in q for term in IMPLEMENTATION_INTENT_TERMS)


def wants_docs_evidence(question: str) -> bool:
    q = question.lower()
    return any(term in q for term in DOC_INTENT_TERMS)


def chunk_search_text(chunk: Dict[str, Any]) -> str:
    return " ".join(
        str(chunk.get(key) or "")
        for key in ["file_path", "symbol_name", "symbol_type", "category", "language", "text"]
    ).lower()


def chunk_term_overlap(chunk: Dict[str, Any], terms: set[str]) -> int:
    haystack = chunk_search_text(chunk)
    return sum(1 for term in terms if term in haystack)


def is_implementation_chunk(chunk: Dict[str, Any]) -> bool:
    if chunk.get("source_type") != "code":
        return False
    if chunk.get("category") == "docs":
        return False
    path = str(chunk.get("file_path") or "").lower()
    return not any(part in path for part in ["/generated_", "generated_plugin", ".g.dart"])


def has_required_implementation_evidence(question: str, chunks: List[Dict[str, Any]]) -> bool:
    if not wants_implementation_evidence(question):
        return True

    terms = extract_query_terms(question)
    return any(
        is_implementation_chunk(chunk) and chunk_term_overlap(chunk, terms) > 0
        for chunk in chunks
    )


def evidence_rank(question: str, chunk: Dict[str, Any]) -> tuple[float, float]:
    terms = extract_query_terms(question)
    score = float(chunk.get("score") or 0)
    overlap = chunk_term_overlap(chunk, terms)
    path = str(chunk.get("file_path") or "").lower()
    category = chunk.get("category")

    if wants_implementation_evidence(question):
        if is_implementation_chunk(chunk):
            score += 0.35
        elif category == "docs":
            score -= 0.12

    if wants_docs_evidence(question) and category == "docs":
        score += 0.12

    for term in terms:
        if term in path:
            score += 0.08
    score += min(overlap * 0.025, 0.25)

    return score, float(chunk.get("raw_score") or 0)


def select_answer_chunks(question: str, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(chunks, key=lambda chunk: evidence_rank(question, chunk), reverse=True)


def build_required_snippet(question: str, chunks: List[Dict[str, Any]]) -> str:
    if not wants_implementation_evidence(question):
        return ""

    terms = extract_query_terms(question)
    candidates = [
        chunk
        for chunk in chunks
        if is_implementation_chunk(chunk) and chunk_term_overlap(chunk, terms) > 0
    ]
    if not candidates:
        return ""

    chunk = max(candidates, key=lambda item: evidence_rank(question, item))
    text = str(chunk.get("text") or "").strip()
    if not text:
        return ""

    citation = format_citation(chunk)
    language = str(chunk.get("language") or "text")
    return f"""
Required implementation evidence:
If the answer includes a code snippet, copy it from this retrieved source. Do not
rewrite class names, method names, routes, error handling, imports, or API calls.

[IMPLEMENTATION SOURCE]
Citation: {citation}

```{language}
{text[:2400]}
```
[/IMPLEMENTATION SOURCE]
""".strip()


def explicit_memory_requested(question: str) -> bool:
    q = question.lower()
    return any(term in q for term in EXPLICIT_MEMORY_TERMS)


def source_mode_for_question(question: str, repo_name: Optional[str]) -> str:
    if explicit_memory_requested(question):
        return "mixed" if repo_name else "memory_only"
    if repo_name:
        return "code_only"
    sources = heuristic_sources(question)
    if sources == ["code"]:
        return "code_only"
    if sources == ["memory"]:
        return "memory_only"
    return "mixed"


def sources_for_mode(source_mode: str) -> List[SourceName]:
    if source_mode == "code_only":
        return ["code"]
    if source_mode == "memory_only":
        return ["memory"]
    return ["code", "memory"]


def heuristic_sources(question: str) -> List[SourceName]:
    q = question.lower()
    wants_code = any(term in q for term in HEURISTIC_CODE_TERMS)
    wants_memory = any(term in q for term in HEURISTIC_MEMORY_TERMS)
    if wants_code and not wants_memory:
        return ["code"]
    if wants_memory and not wants_code:
        return ["memory"]
    return ["code", "memory"]


def fallback_analysis(question: str) -> Dict[str, Any]:
    words = question.split()
    is_complex = len(words) > 18 or any(token in question.lower() for token in ["compare", "how", "why", "and", "across"])
    repo_name = detect_repo_name(question)
    source_mode = source_mode_for_question(question, repo_name)
    sources = sources_for_mode(source_mode)
    return {
        "question_type": "multi_hop" if is_complex else "simple",
        "complexity": "high" if is_complex else "low",
        "needs_multiple_sources": is_complex or len(sources) > 1,
        "main_topics": words[:8],
        "expected_evidence": ["implementation details", "documentation notes"],
        "sources": sources,
        "source_mode": source_mode,
        "detected_repo": repo_name,
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
  "sources": ["code", "memory"],
  "source_mode": "code_only | memory_only | mixed",
  "detected_repo": "repo-name-or-null"
}}
"""
    data = call_llm_json(prompt, fallback)
    data["detected_repo"] = fallback["detected_repo"]
    data["source_mode"] = fallback["source_mode"]
    sources = data.get("sources")
    if not isinstance(sources, list) or not sources:
        data["sources"] = fallback["sources"]
    data["sources"] = sources_for_mode(data["source_mode"])
    return data


def fallback_plan(question: str, analysis: Dict[str, Any]) -> List[Dict[str, str]]:
    sources = analysis.get("sources") or sources_for_mode(analysis.get("source_mode", "mixed"))
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
    allowed_sources = set(analysis.get("sources") or ["code", "memory"])
    for item in raw_plan[:AGENTIC_INITIAL_SUBQUERIES]:
        if not isinstance(item, dict):
            continue
        source = item.get("source")
        if source not in allowed_sources:
            source = (analysis.get("sources") or ["code", "memory"])[0]
        query = str(item.get("query") or question).strip()
        plan.append(
            {
                "sub_question": str(item.get("sub_question") or query).strip(),
                "query": query,
                "source": source,
            }
        )
    return plan or fallback["plan"]


def collection_for_source(source: SourceName) -> str:
    return CODE_COLLECTION if source == "code" else MEMORY_COLLECTION


def build_source_filter(source: SourceName, repo_name: Optional[str]) -> Optional[Filter]:
    if source != "code" or not repo_name:
        return None
    return Filter(
        must=[
            FieldCondition(
                key="repo",
                match=MatchValue(value=repo_name),
            )
        ]
    )


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
    raw_id = payload.get("chunk_id") or f"{source}:{repo_name or ''}:{file_path}:{chunk_index}"
    content_hash = payload.get("content_hash") or hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return {
        "chunk_id": str(raw_id),
        "source_type": source,
        "repo_name": repo_name,
        "file_path": str(file_path),
        "chunk_index": chunk_index,
        "line_start": payload.get("line_start"),
        "line_end": payload.get("line_end"),
        "content_hash": content_hash,
        "score": float(point.score or 0),
        "raw_score": float(point.score or 0),
        "query": query,
        "language": payload.get("language"),
        "category": payload.get("category"),
        "symbol_type": payload.get("symbol_type"),
        "symbol_name": payload.get("symbol_name"),
        "text": text[:MAX_CHUNK_CHARS],
    }


def keyword_boost(chunk: Dict[str, Any], query: str) -> float:
    terms = extract_query_terms(query)
    haystack = chunk_search_text(chunk)
    path = str(chunk.get("file_path") or "").lower()
    boost = 0.0

    for term in sorted(terms):
        if term in haystack:
            boost += 0.025
        if term in path:
            boost += 0.05

    if wants_implementation_evidence(query) and is_implementation_chunk(chunk):
        boost += 0.12
    if wants_docs_evidence(query) and chunk.get("category") == "docs":
        boost += 0.08

    return min(boost, 0.30)


def reject_chunk(rejected: Optional[List[Dict[str, Any]]], chunk: Dict[str, Any], reason: str) -> None:
    if rejected is None:
        return
    rejected.append(
        {
            "reason": reason,
            "source_type": chunk.get("source_type"),
            "repo_name": chunk.get("repo_name"),
            "file_path": chunk.get("file_path"),
            "chunk_index": chunk.get("chunk_index"),
            "score": chunk.get("score"),
            "raw_score": chunk.get("raw_score"),
            "query": chunk.get("query"),
        }
    )


def search_source(
    query: str,
    source: SourceName,
    top_k: int,
    repo_name: Optional[str] = None,
    source_mode: str = "mixed",
    rejected: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    if source == "memory" and source_mode == "code_only":
        reject_chunk(
            rejected,
            {
                "source_type": "memory",
                "repo_name": None,
                "file_path": MEMORY_COLLECTION,
                "chunk_index": None,
                "score": 0,
                "raw_score": 0,
                "query": query,
            },
            "source_mode_code_only",
        )
        return []

    try:
        vector = embedder.encode(query).tolist()
        query_filter = build_source_filter(source, repo_name)
        query_kwargs = {
            "collection_name": collection_for_source(source),
            "query": vector,
            "limit": max(top_k * 4, top_k),
            "with_payload": True,
            "with_vectors": False,
        }
        if query_filter:
            query_kwargs["query_filter"] = query_filter
        try:
            results = client.query_points(**query_kwargs)
        except TypeError:
            query_kwargs.pop("query_filter", None)
            results = client.query_points(**query_kwargs)
    except Exception as exc:
        log_event("search_error", {"query": query, "source": source, "repo_name": repo_name, "error": str(exc)})
        return []

    chunks = []
    for point in results.points:
        chunk = point_to_chunk(point, source, query)
        if source == "code" and repo_name and chunk.get("repo_name") != repo_name:
            reject_chunk(rejected, chunk, "repo_mismatch")
            continue
        chunk["keyword_boost"] = keyword_boost(chunk, query)
        chunk["score"] = float(chunk.get("raw_score") or 0) + float(chunk["keyword_boost"])
        if float(chunk["score"] or 0) < SCORE_THRESHOLD:
            reject_chunk(rejected, chunk, "below_score_threshold")
            continue
        chunks.append(chunk)
        if len(chunks) >= top_k:
            break
    return chunks


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
    path = chunk.get("file_path") or "unknown"
    line_start = chunk.get("line_start")
    line_end = chunk.get("line_end")
    if line_start and line_end:
        return f"{path}:{line_start}-{line_end}"
    if chunk.get("repo_name"):
        return f"{chunk.get('repo_name')}/{path}#chunk-{chunk.get('chunk_index')}"
    return f"{path}#chunk-{chunk.get('chunk_index')}"


def format_evidence(chunks: List[Dict[str, Any]]) -> str:
    parts = []
    total_chars = 0
    for index, chunk in enumerate(chunks, start=1):
        text = chunk.get("text") or ""
        block = f"""
[SOURCE {index}]
Citation: {format_citation(chunk)}
Source type: {chunk.get("source_type")}
Score: {round(float(chunk.get("score") or 0), 4)}
Category: {chunk.get("category")}
Symbol: {chunk.get("symbol_type")} {chunk.get("symbol_name")}

{text}
[/SOURCE {index}]
""".strip()
        if total_chars + len(block) > MAX_CONTEXT_CHARS:
            break
        parts.append(block)
        total_chars += len(block)
    return "\n\n".join(parts) if parts else "No indexed evidence was found."


def evaluate_evidence(question: str, chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not ENABLE_AGENTIC_RETRIEVAL:
        return {
            "enough": bool(chunks),
            "confidence": 0.75 if chunks else 0.0,
            "missing_information": [] if chunks else ["No relevant chunks found"],
            "followup_queries": [],
        }
    fallback_confidence = min(0.95, 0.35 + (len(chunks) * 0.08))
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
  "confidence": 0.0,
  "missing_information": [],
  "followup_queries": []
}}

Use at most {AGENTIC_FOLLOWUP_TOP_K} follow-up queries.
"""
    data = call_llm_json(prompt, fallback)
    confidence = data.get("confidence", fallback["confidence"])
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = fallback["confidence"]
    data["confidence"] = max(0.0, min(1.0, confidence))
    data["enough"] = bool(data.get("enough")) and data["confidence"] >= AGENTIC_MIN_CONFIDENCE
    if not isinstance(data.get("followup_queries"), list):
        data["followup_queries"] = []
    if not isinstance(data.get("missing_information"), list):
        data["missing_information"] = []
    return data


def applied_filters_for(analysis: Dict[str, Any]) -> Dict[str, Any]:
    repo_name = analysis.get("detected_repo")
    return {
        "source_mode": analysis.get("source_mode", "mixed"),
        "code_repo": repo_name if repo_name else None,
        "memory_allowed": analysis.get("source_mode") != "code_only",
    }


def run_simple_retrieval(question: str) -> Dict[str, Any]:
    analysis = fallback_analysis(question)
    repo_name = analysis.get("detected_repo")
    source_mode = analysis.get("source_mode", "mixed")
    rejected_chunks: List[Dict[str, Any]] = []
    plan = [
        {"sub_question": question, "query": question, "source": source}
        for source in sources_for_mode(source_mode)
    ]
    chunks: List[Dict[str, Any]] = []
    for item in plan:
        chunks.extend(
            search_source(
                item["query"],
                item["source"],
                SIMPLE_TOP_K,
                repo_name=repo_name,
                source_mode=source_mode,
                rejected=rejected_chunks,
            )
        )
    chunks = dedupe_chunks(chunks)
    evaluation = evaluate_evidence(question, chunks)
    return {
        "analysis": analysis,
        "detected_repo": repo_name,
        "source_mode": source_mode,
        "applied_filters": applied_filters_for(analysis),
        "plan": plan,
        "queries_used": plan,
        "chunks": chunks,
        "rejected_chunks": rejected_chunks[:50],
        "reranked_chunks": chunks,
        "evaluations": [evaluation],
        "confidence": evaluation["confidence"],
        "stop_reason": "simple_retrieval",
    }


def run_agentic_retrieval(question: str) -> Dict[str, Any]:
    if not ENABLE_INDEX_V2 or not ENABLE_AGENTIC_RETRIEVAL:
        return run_simple_retrieval(question)

    analysis = analyze_question(question)
    repo_name = analysis.get("detected_repo")
    source_mode = analysis.get("source_mode", "mixed")
    plan = build_retrieval_plan(question, analysis)
    all_chunks: List[Dict[str, Any]] = []
    queries_used: List[Dict[str, str]] = []
    evaluations: List[Dict[str, Any]] = []
    rejected_chunks: List[Dict[str, Any]] = []
    stop_reason = "max_steps"

    current_plan = plan
    for step in range(1, AGENTIC_MAX_STEPS + 1):
        step_chunks = []
        for item in current_plan:
            source = item.get("source")
            query = item.get("query") or question
            if source not in {"code", "memory"}:
                continue
            query_record = {
                "step": str(step),
                "sub_question": item.get("sub_question", query),
                "query": query,
                "source": source,
            }
            queries_used.append(query_record)
            top_k = AGENTIC_TOP_K_PER_QUERY if step == 1 else AGENTIC_FOLLOWUP_TOP_K
            step_chunks.extend(
                search_source(
                    query,
                    source,
                    top_k,
                    repo_name=repo_name,
                    source_mode=source_mode,
                    rejected=rejected_chunks,
                )
            )

        before_count = len(all_chunks)
        all_chunks = dedupe_chunks(all_chunks + step_chunks)
        evaluation = evaluate_evidence(question, all_chunks)
        evaluations.append(evaluation)

        log_event(
            "retrieval_step",
            {
                "question": question,
                "step": step,
                "planned_queries": len(current_plan),
                "new_chunks": len(all_chunks) - before_count,
                "total_chunks": len(all_chunks),
                "confidence": evaluation["confidence"],
                "enough": evaluation["enough"],
            },
        )

        if evaluation["enough"]:
            stop_reason = "enough_evidence"
            break
        if len(all_chunks) >= AGENTIC_MAX_TOTAL_CHUNKS:
            stop_reason = "max_total_chunks"
            break
        if len(all_chunks) == before_count and step > 1:
            stop_reason = "no_new_chunks"
            break

        followups = [str(query).strip() for query in evaluation.get("followup_queries", []) if str(query).strip()]
        if not followups:
            stop_reason = "no_followup_queries"
            break
        sources = analysis.get("sources") or sources_for_mode(source_mode)
        current_plan = [
            {
                "sub_question": f"Follow-up evidence for: {query}",
                "query": query,
                "source": sources[index % len(sources)],
            }
            for index, query in enumerate(followups[:AGENTIC_FOLLOWUP_TOP_K])
        ]

    final_evaluation = evaluations[-1] if evaluations else {"confidence": 0.0}
    return {
        "analysis": analysis,
        "detected_repo": repo_name,
        "source_mode": source_mode,
        "applied_filters": applied_filters_for(analysis),
        "plan": plan,
        "queries_used": queries_used,
        "chunks": all_chunks,
        "rejected_chunks": rejected_chunks[:50],
        "reranked_chunks": all_chunks,
        "evaluations": evaluations,
        "confidence": final_evaluation.get("confidence", 0.0),
        "stop_reason": stop_reason,
    }


def build_final_answer(question: str, trace: Dict[str, Any], temperature: float, max_tokens: int) -> str:
    chunks = select_answer_chunks(question, trace.get("chunks", []))
    trace["answer_chunks"] = chunks
    citations = [format_citation(chunk) for chunk in chunks]
    evidence_gate = ""
    if not has_required_implementation_evidence(question, chunks):
        evidence_gate = (
            "\nImportant evidence gate: The user asked for implementation/code evidence, "
            "but no retrieved source contains matching implementation code. State that "
            "the indexed evidence does not include the requested implementation snippet. "
            "Do not provide a generic or example code snippet.\n"
        )
    prompt = f"""
You are an agentic RAG assistant connected to private code and memory indexes.

Answer the user question using the retrieved evidence. If evidence is incomplete,
say what is uncertain. Cite sources inline using [SOURCE N] references and include
a short Sources section.

Rules:
- Use only the evidence below.
- Do not invent backend systems, files, functions, or snippets.
- If you include a code snippet, copy it only from a retrieved SOURCE.
- For backend claims such as Firebase, Supabase, REST APIs, or custom servers,
  require direct evidence from imports, config, README, or code.
- Cite only sources you actually used in the answer.
{evidence_gate}
{build_required_snippet(question, chunks)}

User question:
{question}

Retrieval confidence:
{trace.get("confidence")}

Stop reason:
{trace.get("stop_reason")}

Evidence:
{format_evidence(chunks)}

Known citations:
{json.dumps(citations, ensure_ascii=False)}
"""
    try:
        return call_llm_messages(
            [
                {"role": "system", "content": "You answer with grounded citations and do not invent evidence."},
                {"role": "user", "content": prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except Exception as exc:
        log_event("final_answer_error", {"error": str(exc)})
        if not chunks:
            return f"I could not find indexed evidence for this question. Model call failed: {exc}"
        sources = "\n".join(f"- [SOURCE {i}] {format_citation(chunk)}" for i, chunk in enumerate(chunks, start=1))
        return (
            "I found relevant indexed evidence, but the final model call failed. "
            f"Error: {exc}\n\nSources:\n{sources}"
        )


def answer_question(question: str, temperature: float = 0.2, max_tokens: int = 2048) -> Dict[str, Any]:
    trace = run_agentic_retrieval(question)
    answer = build_final_answer(question, trace, temperature, max_tokens)
    if not has_required_implementation_evidence(question, trace.get("chunks", [])):
        required_note = "The indexed evidence does not include the requested implementation snippet."
        if required_note not in answer:
            answer = f"{required_note}\n\n{answer}"
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
    analysis = fallback_analysis(req.query)
    repo_name = req.repo or analysis.get("detected_repo")
    source_mode = "mixed"
    sources: List[SourceName]
    if req.source == "code":
        sources = ["code"]
        source_mode = "code_only"
    elif req.source == "memory":
        sources = ["memory"]
        source_mode = "memory_only"
    else:
        source_mode = analysis.get("source_mode", "mixed")
        sources = sources_for_mode(source_mode)
    chunks: List[Dict[str, Any]] = []
    rejected_chunks: List[Dict[str, Any]] = []
    for source in sources:
        chunks.extend(
            search_source(
                req.query,
                source,
                req.top_k or SIMPLE_TOP_K,
                repo_name=repo_name,
                source_mode=source_mode,
                rejected=rejected_chunks,
            )
        )
    results = dedupe_chunks(chunks)
    return {
        "query": req.query,
        "detected_repo": repo_name,
        "source_mode": source_mode,
        "applied_filters": {
            "source_mode": source_mode,
            "code_repo": repo_name if repo_name else None,
            "memory_allowed": source_mode != "code_only",
        },
        "results": results,
        "rejected_chunks": rejected_chunks[:50],
        "reranked_chunks": results,
    }


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

    result = answer_question(
        user_question,
        temperature=req.temperature or 0.2,
        max_tokens=req.max_tokens or 2048,
    )

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
                    "content": result["answer"],
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
