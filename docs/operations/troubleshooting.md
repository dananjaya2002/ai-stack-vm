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

## Dashboard Shows Missing Memory Or Code Logs

The dashboard reads structured proxy event files from shared Docker volumes.
These are separate from container stdout, which remains available through:

```bash
./ai-stack logs memory
./ai-stack logs code
```

File logging is enabled by default for both proxies. Check `.env` if the
dashboard reports `logging disabled`:

```env
MEMORY_API_LOGS=true
MEMORY_API_LOG_FILE=/logs/memory/memory_api.log
CODE_PROXY_LOGS=true
CODE_PROXY_LOG_FILE=/logs/code/code_proxy.log
```

Each proxy creates its log and writes a startup event. After changing `.env`,
restart the main stack and dashboard so both receive the new settings:

```bash
./ai-stack restart
./ai-stack dashboard
```

`no events yet` means the file is readable but empty. `log unavailable` means
logging is enabled but the configured file cannot be found or read; check the
proxy container logs and the `memory_logs` or `code_logs` Compose volume.

Dashboard job and watcher output is temporary. It is kept in memory for live
viewing and is cleared whenever the dashboard container restarts. The `*.log`
entry in `scripts/config/code_watch.json` intentionally prevents log writes
from triggering code re-indexing; it does not disable proxy logs.

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
