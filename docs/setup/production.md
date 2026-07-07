# Production Setup

Production mode enables required proxy auth and dashboard login. Use this mode
when exposing Open WebUI or the dashboard outside your local machine.

## Required `.env` Values

```env
SECURITY_MODE=production
AI_STACK_API_KEY=<long-random-secret>

DASHBOARD_AUTH_MODE=auto
DASHBOARD_ADMIN_USERNAME=admin
DASHBOARD_ADMIN_PASSWORD_HASH=sha256:<password-hash>
DASHBOARD_SESSION_SECRET=<long-random-secret>

BIND_HOST=127.0.0.1
OPEN_WEBUI_BIND_HOST=0.0.0.0
DASHBOARD_BIND_HOST=0.0.0.0
LLM_BASE_URL=http://vm-llama:8082/v1
```

Keep `BIND_HOST=127.0.0.1` unless you intentionally expose model, proxy, and
Qdrant ports.

## Generate Secrets

Password hash:

```bash
python3 -c 'import hashlib,getpass; print("sha256:" + hashlib.sha256(getpass.getpass("Dashboard password: ").encode()).hexdigest())'
```

Random secrets:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
```

Use one random value for `AI_STACK_API_KEY` and one for
`DASHBOARD_SESSION_SECRET`.

## Restart

```bash
./ai-stack init
./ai-stack build
./ai-stack up
./ai-stack dashboard
./ai-stack agentic-rag up
./ai-stack status
```

## Verify Auth

Without token, proxy requests should fail:

```bash
curl -i http://localhost:9001/v1/models
```

With token, they should pass:

```bash
source .env
curl -i -H "Authorization: Bearer $AI_STACK_API_KEY" http://localhost:9001/v1/models
```

## Related Docs

- [Production hardening](../security/production-hardening.md)
- [Health checks](../operations/health-checks.md)
- [Open WebUI connections](../examples/open-webui-connections.md)
