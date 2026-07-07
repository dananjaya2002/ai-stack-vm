# OpenAI-Compatible APIs

The model server and RAG proxies expose endpoints compatible with OpenAI-style
clients.

## Services

| Service | Host URL | Docker/Open WebUI URL |
|---|---|---|
| llama.cpp | `http://localhost:8082/v1` | `http://vm-llama:8082/v1` |
| code-proxy | `http://localhost:9001/v1` | `http://code-proxy:9001/v1` |
| memory-proxy | `http://localhost:9002/v1` | `http://memory-proxy:9002/v1` |
| agentic-rag | `http://localhost:9200/v1` | `http://agentic-rag:9200/v1` |

## Endpoints

```text
GET  /v1/models
POST /v1/chat/completions
```

The RAG proxy services also expose helper endpoints:

```text
POST /search
POST /ask
```

## Chat Example

```bash
source .env
curl -X POST http://localhost:9001/v1/chat/completions \
  -H "Authorization: Bearer $AI_STACK_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "code-proxy",
    "messages": [
      {"role": "user", "content": "Where is dashboard authentication handled?"}
    ]
  }'
```

Omit the authorization header in unauthenticated development mode.

## Related Docs

- [Agentic RAG API](agentic-rag.md)
- [Open WebUI connections](../examples/open-webui-connections.md)
- [Security](../security/README.md)
