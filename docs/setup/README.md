# Setup

Use this section to install, configure, and run AI Stack VM.

## Recommended First Run

```bash
chmod +x ./ai-stack
./ai-stack install --compute auto
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

- [Installation](installation.md)
- [Hardware detection and compute resolution](hardware-detection.md)
- [NVIDIA GPU installation](gpu-installation.md)
- [Local development](local-development.md)
- [Production setup](production.md)
- [Configuration](configuration.md)
- [Runtime storage](runtime-storage.md)
- [Open WebUI runtime settings](open-webui.md)

## Important Model

The root `.env` is the single runtime configuration source. `./ai-stack init`
creates it if missing and backs it up before backfilling or changing existing
values.

## Related Docs

- [CLI guide](../cli/README.md)
- [Security](../security/README.md)
- [Operations](../operations/README.md)
