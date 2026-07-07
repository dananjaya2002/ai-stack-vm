# Backup And Restore

The project includes `backup-ai-stack.sh` for local backup helpers.

## Backup

```bash
bash backup-ai-stack.sh
```

Backups are written under:

```text
$AI_STACK_HOME/backups
```

The script backs up runtime memory folders and the root `.env` when present.

## Restore Considerations

Before relying on backup output, verify:

- model files are available under `$AI_STACK_HOME/models`
- Qdrant/Open WebUI data location matches the current Compose volume strategy
- root `.env` values match the target machine
- secrets are not committed to Git

## Related Docs

- [Configuration](../setup/configuration.md)
- [Security](../security/README.md)
- [Operations](README.md)
