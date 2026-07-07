# Open WebUI Connections

Open WebUI runs at:

```text
http://localhost:8080
```

If accessing from another machine, use the VM IP or your forwarded address.

## Docker/Internal URLs

Configure OpenAI-compatible connections inside Open WebUI with:

```text
http://vm-llama:8082/v1
http://code-proxy:9001/v1
http://memory-proxy:9002/v1
http://agentic-rag:9200/v1
```

Use `AI_STACK_API_KEY` for proxy and Agentic RAG connections when
`SECURITY_MODE=production`.

## Host URLs

From the VM host:

```text
http://localhost:8082/v1
http://localhost:9001/v1
http://localhost:9002/v1
http://localhost:9200/v1
```

## Related Docs

- [Production setup](../setup/production.md)
- [OpenAI-compatible APIs](../api/openai-compatible.md)
- [Troubleshooting](../operations/troubleshooting.md)
