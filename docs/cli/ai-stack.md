# `./ai-stack` Command Reference

```text
./ai-stack doctor
./ai-stack install
./ai-stack init
./ai-stack profile laptop|vm16|vm60
./ai-stack model list
./ai-stack model path
./ai-stack model use <file.gguf>
./ai-stack model download [url]
./ai-stack build
./ai-stack up
./ai-stack dashboard
./ai-stack agentic-rag [up|down|status|logs]
./ai-stack down
./ai-stack restart
./ai-stack status
./ai-stack smoke [production]
./ai-stack qdrant collections
./ai-stack qdrant reset memory|code|demo
./ai-stack benchmark
./ai-stack logs [llama|qdrant|code|memory|webui|dashboard|agentic-rag|all]
./ai-stack index memory
./ai-stack index code <repo-path>
./ai-stack search code "query"
./ai-stack search memory "query"
./ai-stack demo [clean|run|reset-vectors]
```

## Notes

- `init` creates runtime directories and backfills missing `.env` keys.
- `dashboard` builds/runs the dashboard service.
- `agentic-rag` is optional and should be started after the main stack.
- `status` uses `AI_STACK_API_KEY` automatically when it is set in `.env`.
- `smoke` runs end-to-end curl checks for the stack; `smoke production` also
  verifies bearer auth behavior.
- `qdrant reset ...` commands require typed confirmation before deleting data.
- `benchmark` writes `docs/benchmarks/latest.md`.
- `demo run` is the golden path for copying demo data, indexing it, and printing
  sample questions.

## Related Docs

- [Configuration](../setup/configuration.md)
- [Health checks](../operations/health-checks.md)
- [Maintenance](maintenance.md)
