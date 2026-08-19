# Setup

Use this section to install, configure, and run AI Stack VM.

## Recommended First Run

```bash
chmod +x ./ai-stack
./ai-stack install
```

Manual setup:

```bash
./ai-stack doctor
./ai-stack init
./ai-stack model download
./ai-stack build
./ai-stack up
./ai-stack status
```

## Setup Guides

- [Local development](local-development.md)
- [Production setup](production.md)
- [Configuration](configuration.md)
- [Runtime storage](runtime-storage.md)
- [Open WebUI runtime settings](open-webui.md)

## Important Model

The root `.env` is the single runtime configuration source. `./ai-stack init`
creates it if missing and backfills missing keys without overwriting existing
values.

## Related Docs

- [CLI guide](../cli/README.md)
- [Security](../security/README.md)
- [Operations](../operations/README.md)
