# Production Hardening

## Keep Core Services Private

Keep:

```env
BIND_HOST=127.0.0.1
```

This keeps Qdrant, llama.cpp, memory-proxy, code-proxy, and Agentic RAG bound to
localhost unless you intentionally expose them.

## Exposed Browser Services

These may be exposed for browser access:

```env
OPEN_WEBUI_BIND_HOST=0.0.0.0
DASHBOARD_BIND_HOST=0.0.0.0
```

Use HTTPS through a reverse proxy when crossing a network boundary. See:

```text
docker/caddy/Caddyfile.example
```

## Require Auth

Use:

```env
SECURITY_MODE=production
AI_STACK_API_KEY=<long-random-secret>
DASHBOARD_AUTH_MODE=auto
DASHBOARD_ADMIN_PASSWORD_HASH=sha256:<hash>
DASHBOARD_SESSION_SECRET=<long-random-secret>
```

## Secret Hygiene

Do not commit:

- `.env`
- API keys
- dashboard password hashes for real deployments
- model files
- logs
- Qdrant/Open WebUI runtime data
- private memory or repositories

## Related Docs

- [Security overview](README.md)
- [Production setup](../setup/production.md)
- [Configuration](../setup/configuration.md)
