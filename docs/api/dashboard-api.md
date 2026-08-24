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
GET  /api/dashboard/settings
GET  /api/dashboard/logs?source=dashboard|watchers|memory|code|agentic-rag
POST /api/dashboard/logs/reset
POST /api/dashboard/log-capture
PUT  /api/dashboard/config
POST /api/dashboard/config/reset
```

The configuration response includes friendly labels, descriptions, defaults,
types, and allowed ranges for dashboard-editable non-secret `.env` values.
Saving or resetting configuration requires container recreation before the new
values become active.

`/api/dashboard/status` checks llama.cpp, Qdrant, memory folders, system usage,
logs, and watcher state.

`/api/dashboard/settings` returns non-secret runtime values such as service
URLs, auth mode, security mode, collection names, and log file paths.

## Qdrant Operations

```text
GET  /api/dashboard/qdrant/collections
POST /api/dashboard/qdrant/reset
```

Reset requests require a typed confirmation:

```json
{
  "target": "demo",
  "confirmation": "reset demo"
}
```

Supported targets are `memory`, `code`, and `demo`. `memory` and `code` delete
the configured collections. `demo` deletes vectors with known demo payload
markers and may return non-fatal `warnings` when a demo collection is missing.

## Files And Uploads

```text
GET    /api/dashboard/files?scope=engineering|code&path=<path>
DELETE /api/dashboard/files
POST   /api/dashboard/upload
```

File operations are constrained to the mounted engineering-memory and
code-memory roots.

Document-memory upload accepts Markdown (`.md`) files only. A successful upload
confirms that the file was saved; indexing is the separate step that chunks and
embeds its content. The browser file picker filters unsupported extensions,
and the API independently rejects unsupported types with HTTP 415. Code-memory
upload supports ZIP archives and the source/configuration file extensions shown
by the dashboard.

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
