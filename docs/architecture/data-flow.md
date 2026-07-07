# Data Flow

AI Stack VM has two main data flows: indexing and answering.

## Indexing Flow

```text
engineering markdown files
  -> memory indexer
  -> embeddings
  -> Qdrant engineering-memory collection

code repositories
  -> code indexer
  -> chunking + symbol metadata
  -> embeddings
  -> Qdrant code-memory collection
```

Indexing can be started from:

- `./ai-stack index memory`
- `./ai-stack index code <repo-path>`
- Dashboard Indexing tab
- Dashboard watcher controls

## Answering Flow

```text
user question
  -> Open WebUI / curl / dashboard debug flow
  -> memory-proxy, code-proxy, or agentic-rag
  -> Qdrant retrieval
  -> prompt with retrieved context
  -> vm-llama
  -> answer
```

## Agentic RAG Flow

```text
question
  -> analyze question
  -> build retrieval plan
  -> search memory/code collections
  -> evaluate evidence
  -> optional follow-up search
  -> answer with citations
```

Debug this flow with:

```bash
curl -X POST http://localhost:9200/v1/rag/debug \
  -H "Content-Type: application/json" \
  -d '{"question":"How do dashboard auth and proxy auth connect?"}'
```

Use `Authorization: Bearer $AI_STACK_API_KEY` when `SECURITY_MODE=production`.

## Related Docs

- [Indexing operations](../operations/indexing.md)
- [Agentic RAG API](../api/agentic-rag.md)
- [Curl examples](../examples/curl-examples.md)
