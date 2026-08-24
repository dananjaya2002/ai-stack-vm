# Agentic RAG API

`agentic-rag` is an optional connector that performs multi-step retrieval across
memory and code collections.

## Start

```bash
./ai-stack up
./ai-stack agentic-rag up
```

## Endpoints

```text
GET  /
GET  /v1/models
POST /search
POST /ask
POST /v1/rag/debug
POST /v1/chat/completions
```

## Debug Example

```bash
source .env
curl -X POST http://localhost:9200/v1/rag/debug \
  -H "Authorization: Bearer $AI_STACK_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"question":"How do the dashboard, proxy security, and compose files connect?"}'
```

## Configuration

Agentic RAG settings live in root `.env`, including:

- `ENABLE_AGENTIC_RETRIEVAL`
- `AGENTIC_MAX_STEPS`
- `AGENTIC_INITIAL_SUBQUERIES`
- `AGENTIC_FOLLOWUP_TOP_K`
- `AGENTIC_MAX_TOTAL_CHUNKS`
- `AGENTIC_MIN_CONFIDENCE`
- `AGENTIC_TOP_K_PER_QUERY`

Questions that name a memory document, such as `Runbook.md`, first perform an
exact, case-insensitive filename lookup. Matching chunks are reconstructed in
document order and bypass multi-step planning. Reindex existing memory documents
after upgrading so the normalized `file_name` payload is available; a legacy
payload scan remains as a compatibility fallback.

Answers reference code with normalized repository-relative locations such as
`repo/src/service.py:10-24`. Memory evidence is displayed as a filename only,
such as `Runbook.md`. Numbered placeholders such as `[Source 1]` are not exposed
in buffered or streamed responses. Reindex code after upgrading to add accurate
line ranges; legacy index payloads continue to return path and chunk references.

## Related Docs

- [Data flow](../architecture/data-flow.md)
- [Curl examples](../examples/curl-examples.md)
- [Configuration](../setup/configuration.md)
