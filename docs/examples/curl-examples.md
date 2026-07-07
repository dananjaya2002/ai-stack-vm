# Curl Examples

Use these examples from the VM host.

## Development Mode

If `SECURITY_MODE=development` and `AI_STACK_API_KEY` is empty:

```bash
curl http://localhost:9001/v1/models
curl http://localhost:9002/v1/models
curl http://localhost:9200/v1/models
```

## Production Mode

```bash
source .env
curl -H "Authorization: Bearer $AI_STACK_API_KEY" http://localhost:9001/v1/models
curl -H "Authorization: Bearer $AI_STACK_API_KEY" http://localhost:9002/v1/models
curl -H "Authorization: Bearer $AI_STACK_API_KEY" http://localhost:9200/v1/models
```

## Code Search

```bash
source .env
curl -X POST http://localhost:9001/search \
  -H "Authorization: Bearer $AI_STACK_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query":"Where is dashboard authentication handled?"}'
```

## Memory Ask

```bash
source .env
curl -X POST http://localhost:9002/ask \
  -H "Authorization: Bearer $AI_STACK_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query":"What do we know about deployment?"}'
```

## Agentic Debug

```bash
source .env
curl -X POST http://localhost:9200/v1/rag/debug \
  -H "Authorization: Bearer $AI_STACK_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"question":"How do dashboard status checks reach llama and Qdrant?"}'
```

## Related Docs

- [OpenAI-compatible APIs](../api/openai-compatible.md)
- [Agentic RAG API](../api/agentic-rag.md)
- [Security](../security/README.md)
