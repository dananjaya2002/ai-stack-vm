# Dashboard API

The dashboard API is served by FastAPI on port `9100`. It powers the React UI
and can also be used directly for operations.

## Auth Endpoints

```text
GET  /api/dashboard/auth/status
POST /api/dashboard/auth/login
POST /api/dashboard/auth/logout
```

In production mode, all dashboard API routes except auth routes require a valid
dashboard session cookie.

## Status And Logs

```text
GET  /api/dashboard/status
GET  /api/dashboard/logs?source=dashboard|watchers|memory|code
POST /api/dashboard/log-capture
```

`/api/dashboard/status` checks llama.cpp, Qdrant, memory folders, system usage,
logs, and watcher state.

## Files And Uploads

```text
GET    /api/dashboard/files?scope=engineering|code&path=<path>
DELETE /api/dashboard/files
POST   /api/dashboard/upload
```

File operations are constrained to the mounted engineering-memory and
code-memory roots.

## Repositories, Indexing, Jobs, Watchers

```text
POST /api/dashboard/repos/clone
POST /api/dashboard/index
GET  /api/dashboard/jobs
GET  /api/dashboard/jobs/{job_id}
GET  /api/dashboard/watchers
POST /api/dashboard/watchers/{scope}/start
POST /api/dashboard/watchers/{scope}/stop
```

Dashboard clone operations support HTTPS repository URLs. Private repo tokens
are passed as one-time values and redacted from job output.

## Related Docs

- [Dashboard operations](../operations/README.md)
- [Indexing](../operations/indexing.md)
- [Production setup](../setup/production.md)
