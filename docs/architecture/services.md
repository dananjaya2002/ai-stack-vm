# Services

This page explains the responsibility and boundary of each runtime service.

## `vm-llama`

Runs `ghcr.io/ggml-org/llama.cpp:server` with the GGUF model mounted from
`$AI_STACK_HOME/models`. It exposes an OpenAI-compatible API on port `8082`.

## `qdrant`

Stores embeddings for:

- `engineering-memory`
- `code-memory`

The proxies and Agentic RAG connector query Qdrant over the Compose network.

## `memory-proxy`

Exposes OpenAI-compatible chat and helper search endpoints over markdown notes
mounted at `/memory`. It uses the `engineering-memory` collection.

## `code-proxy`

Exposes OpenAI-compatible chat and helper search endpoints over repositories
mounted at `/code-memory`. It uses the `code-memory` collection.

## `agentic-rag`

Runs optional multi-step retrieval. It can search both memory and code
collections, evaluate evidence, run follow-up searches, and return an answer
with citations.

## `dashboard`

Provides browser-based operations:

- service health
- logs
- file browsing/deletion
- uploads
- repo clone/update
- indexing jobs
- watcher start/stop

Dashboard auth is controlled by root `.env`.

## Related Docs

- [Data flow](data-flow.md)
- [Dashboard API](../api/dashboard-api.md)
- [Operations](../operations/README.md)
