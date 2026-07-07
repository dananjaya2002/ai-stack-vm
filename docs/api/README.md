# API Reference

AI Stack VM exposes OpenAI-compatible APIs for chat clients and dashboard APIs
for operations.

## API Groups

- [OpenAI-compatible APIs](openai-compatible.md): llama.cpp, memory-proxy,
  code-proxy, and Agentic RAG `/v1` surfaces.
- [Dashboard API](dashboard-api.md): status, settings, Qdrant operations,
  files, logs, uploads, jobs, watchers, and dashboard auth.
- [Agentic RAG API](agentic-rag.md): search, ask, debug, and chat endpoints.

## Authentication

When `SECURITY_MODE=production`, proxy and Agentic RAG requests require:

```http
Authorization: Bearer <AI_STACK_API_KEY>
```

Dashboard browser auth uses HTTP-only session cookies after login.

## Related Docs

- [Curl examples](../examples/curl-examples.md)
- [Production setup](../setup/production.md)
- [Security](../security/README.md)
