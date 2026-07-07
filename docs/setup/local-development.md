# Local Development

Local development mode is optimized for quick testing on a laptop, VM, or
private development host.

## Default Security

Use:

```env
SECURITY_MODE=development
AI_STACK_API_KEY=
DASHBOARD_AUTH_MODE=auto
```

In this mode:

- proxy bearer auth is optional
- dashboard login is not required
- ports stay controlled by the bind settings in `.env`

## Start Services

```bash
./ai-stack init
./ai-stack build
./ai-stack up
./ai-stack dashboard
./ai-stack status
```

Optional Agentic RAG:

```bash
./ai-stack agentic-rag up
```

## Frontend Development

Dashboard frontend source lives in `scripts/dashboard/frontend`.

```bash
cd scripts/dashboard/frontend
npm install
npm run typecheck
npm run build
```

Do not commit `node_modules` or build output.

## Related Docs

- [Configuration](configuration.md)
- [Dashboard API](../api/dashboard-api.md)
- [Troubleshooting](../operations/troubleshooting.md)
