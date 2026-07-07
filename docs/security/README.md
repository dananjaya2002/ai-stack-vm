# Security

AI Stack VM is local-first. Treat model endpoints, indexed memory, code
repositories, dashboard uploads, and logs as private.

## Main Controls

- Root `.env` controls development or production mode.
- Proxy and Agentic RAG APIs use bearer auth in production.
- Dashboard uses login sessions in production.
- Bind addresses control network exposure.

## Important Settings

```env
SECURITY_MODE=production
AI_STACK_API_KEY=<long-random-secret>
DASHBOARD_AUTH_MODE=auto
DASHBOARD_ADMIN_PASSWORD_HASH=sha256:<hash>
DASHBOARD_SESSION_SECRET=<long-random-secret>
BIND_HOST=127.0.0.1
```

## More

- [Production hardening](production-hardening.md)
- [Repository security policy](../../SECURITY.md)
- [Production setup](../setup/production.md)
