# Configuration

AI Stack VM uses one root `.env` file as the runtime source for Compose and all
services. The public template is [`.env.example`](../../.env.example).

## Main Sections

| Section | Purpose |
|---|---|
| AI Stack runtime | Runtime root such as `AI_STACK_HOME`. |
| Model selection | GGUF model name, file, URL, and profile. |
| Network binding | Host bind settings for service exposure. |
| Security | Production/development mode, bearer key, rate limits. |
| Dashboard login | Dashboard username, password hash, session secret. |
| llama.cpp runtime | Threads, context, batch, CPU/memory limits. |
| Shared retrieval services | Qdrant collections, LLM base URL, embedding model. |
| Memory proxy | Memory retrieval and logging settings. |
| Code proxy | Code retrieval and logging settings. |
| Agentic RAG | Multi-step retrieval tuning settings. |

## Important URLs

Inside Compose, use service names:

```env
LLM_BASE_URL=http://vm-llama:8082/v1
QDRANT_HOST=qdrant
```

From the VM host or laptop with port forwarding, use localhost or the VM IP.

## Backfill Missing Keys

For older `.env` files:

```bash
./ai-stack init
```

This appends missing keys and keeps existing values.

## Related Docs

- [Production setup](production.md)
- [Services](../architecture/services.md)
- [Security](../security/README.md)
