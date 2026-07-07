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

## Related Docs

- [Data flow](../architecture/data-flow.md)
- [Curl examples](../examples/curl-examples.md)
- [Configuration](../setup/configuration.md)
