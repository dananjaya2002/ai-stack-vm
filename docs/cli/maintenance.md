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

## Related Docs

- [Backup and restore](../operations/backup-restore.md)
- [Troubleshooting](../operations/troubleshooting.md)
- [Configuration](../setup/configuration.md)
