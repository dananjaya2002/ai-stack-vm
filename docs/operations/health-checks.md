# Health Checks

## CLI Status

```bash
./ai-stack status
```

Expected healthy services:

```text
qdrant: healthy
llama: healthy
code-proxy: healthy
memory-proxy: healthy
agentic-rag: healthy
```

Agentic RAG is optional; it must be started with:

```bash
./ai-stack agentic-rag up
```

## Dashboard Status

```bash
curl http://localhost:9100/api/dashboard/status
```

In production mode, use the browser login flow for the dashboard UI.

## API Checks

```bash
source .env
curl -H "Authorization: Bearer $AI_STACK_API_KEY" http://localhost:9001/v1/models
curl -H "Authorization: Bearer $AI_STACK_API_KEY" http://localhost:9002/v1/models
curl -H "Authorization: Bearer $AI_STACK_API_KEY" http://localhost:9200/v1/models
```

## Related Docs

- [Troubleshooting](troubleshooting.md)
- [Curl examples](../examples/curl-examples.md)
- [Production setup](../setup/production.md)
