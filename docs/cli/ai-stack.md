# `./ai-stack` Command Reference

```text
./ai-stack doctor
./ai-stack hardware
./ai-stack compute status|auto|cpu|gpu
./ai-stack install [--compute auto|cpu|gpu]
./ai-stack init
./ai-stack profile laptop|vm16|vm60
./ai-stack model list
./ai-stack model path
./ai-stack model add [options]
./ai-stack model use <file.gguf>
./ai-stack model download [url]
./ai-stack build
./ai-stack up
./ai-stack dashboard
./ai-stack agentic-rag [up|down|status|logs]
./ai-stack down
./ai-stack restart
./ai-stack apply-config
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
- `hardware` prints a read-only host, storage, engine, port, and GPU report.
- `compute` reports or persists CPU/GPU intent; changes require an image rebuild.
- `install --compute` has precedence over existing `COMPUTE_MODE`.
- `dashboard` builds/runs the dashboard service.
- `agentic-rag` is optional and should be started after the main stack.
- `status` uses `AI_STACK_API_KEY` automatically when it is set in `.env`.
- `model add` opens an interactive wizard for a direct GGUF URL, downloads the
  file, and activates it in `.env`. Pass `--help` for non-interactive options.
  The command accepts single-file models compatible with llama.cpp; run
  `apply-config` afterward to update a running stack.
- `apply-config` recreates the model, proxy, Agentic RAG, and dashboard containers
  with the current `.env` values without rebuilding images.
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
