# Troubleshooting

## Dashboard Shows Llama Or Qdrant As FAIL

If `./ai-stack status` is healthy but dashboard overview fails, check dashboard
container networking values in `docker-compose.dashboard.yml`:

```yaml
LLAMA_BASE_URL: ${LLM_BASE_URL:-http://vm-llama:8082/v1}
QDRANT_URL: http://qdrant:6333
```

Inside containers, do not use `localhost` for llama or Qdrant.

## Memory Proxy Not Responding

Check logs:

```bash
./ai-stack logs memory
```

Then verify:

```bash
curl -i http://localhost:9002/v1/models
```

In production:

```bash
source .env
curl -i -H "Authorization: Bearer $AI_STACK_API_KEY" http://localhost:9002/v1/models
```

## Duplicate Dashboard Containers

The dashboard compose file includes an `indexer` helper. It should not stay
running. Remove a stale container with:

```bash
podman stop ai-stack-vm_indexer_1
podman rm ai-stack-vm_indexer_1
```

## Production Auth Fails

Verify `.env` has:

```env
SECURITY_MODE=production
AI_STACK_API_KEY=<value>
DASHBOARD_AUTH_MODE=auto
DASHBOARD_ADMIN_PASSWORD_HASH=sha256:<hash>
DASHBOARD_SESSION_SECRET=<value>
```

Then restart:

```bash
./ai-stack restart
./ai-stack dashboard
```

## Related Docs

- [Health checks](health-checks.md)
- [Production setup](../setup/production.md)
- [Dashboard API](../api/dashboard-api.md)
