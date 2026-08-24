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
agentic-rag: not started (optional)
```

Agentic RAG is optional; it must be started with:

```bash
./ai-stack agentic-rag up
```

Configured and observed embedding compute can be inspected with:

```bash
./ai-stack compute status
```

After `up`, the CLI verifies CPU/CUDA wheel identity, CUDA availability,
explicit embedding device, and a real embedding. Dashboard and Agentic RAG are
verified when each optional service starts.

## Smoke Test

Use the smoke command when you want a pass/fail readiness check instead of a
human-readable status summary:

```bash
./ai-stack smoke
```

In production mode, this also validates that proxy calls fail without a bearer
token and pass with `AI_STACK_API_KEY`:

```bash
./ai-stack smoke production
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
- [CLI maintenance](../cli/maintenance.md)
