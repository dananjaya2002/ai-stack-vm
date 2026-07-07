# Maintenance Flows

## Rebuild After Code Changes

```bash
./ai-stack build
./ai-stack up
./ai-stack dashboard
./ai-stack agentic-rag up
```

## Restart Services

```bash
./ai-stack restart
```

Restart one service:

```bash
./ai-stack restart memory-proxy
```

## View Logs

```bash
./ai-stack logs all
./ai-stack logs llama
./ai-stack logs qdrant
./ai-stack logs code
./ai-stack logs memory
./ai-stack logs webui
./ai-stack logs dashboard
./ai-stack logs agentic-rag
```

## Change Model

```bash
./ai-stack model list
./ai-stack model use <file.gguf>
./ai-stack restart vm-llama
```

## Smoke Test

```bash
./ai-stack smoke
```

For production mode with `AI_STACK_API_KEY` set:

```bash
./ai-stack smoke production
```

## Qdrant Lifecycle

```bash
./ai-stack qdrant collections
./ai-stack qdrant reset demo
./ai-stack qdrant reset memory
./ai-stack qdrant reset code
```

Reset commands prompt for `reset demo`, `reset memory`, or `reset code`.

## Benchmarks

```bash
./ai-stack benchmark
```

The report is written to [latest benchmark](../benchmarks/latest.md).

## Related Docs

- [Backup and restore](../operations/backup-restore.md)
- [Troubleshooting](../operations/troubleshooting.md)
- [Configuration](../setup/configuration.md)
- [Benchmarks](../benchmarks/README.md)
