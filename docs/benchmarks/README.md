# Benchmarks

Use this folder for lightweight, reproducible measurements from a real VM or
developer workstation.

## Run

```bash
./ai-stack benchmark
```

The command checks:

- llama.cpp `/v1/models`
- llama.cpp short chat completion
- dashboard `/api/dashboard/status`
- memory-proxy `/v1/models`
- code-proxy `/v1/models`
- Agentic RAG `/v1/models`

The latest output is written to `docs/benchmarks/latest.md`.

## Notes

- Run benchmarks after `./ai-stack up`, `./ai-stack dashboard`, and
  `./ai-stack agentic-rag up`.
- Production mode automatically uses `AI_STACK_API_KEY` when it is set in
  `.env`.
- Commit representative benchmark output only when it does not reveal private
  hostnames, paths, or data.

## Related Docs

- [CLI maintenance](../cli/maintenance.md)
- [Health checks](../operations/health-checks.md)
- [Root README benchmarks](../../README.md#benchmarks)
