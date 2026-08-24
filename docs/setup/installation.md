# Installation

## Recommended commands

```bash
./ai-stack install --compute auto
```

Use `--compute cpu` for the smallest portable images or `--compute gpu` when an
NVIDIA GPU must be used. An explicit GPU request fails before model download or
image build if a prerequisite is unavailable.

Precedence is the command-line option, existing `COMPUTE_MODE`, then `auto`.
Before backfilling or changing an existing `.env`, the CLI creates a timestamped
`.env.backup-YYYYMMDD-HHMMSS` copy.

## Installation stages

1. Check `git`, `curl`, `awk`, container engine, and Compose.
2. Detect hardware and filesystems.
3. Resolve CPU or NVIDIA backend.
4. Recommend and select a GGUF model.
5. Enforce storage minimums.
6. Create/backfill `.env` and runtime directories.
7. Resume or download the model.
8. Build images with the resolved PyTorch backend.
9. Start the main stack.
10. Verify Torch identity, CUDA availability/device, and a real embedding.

External build/download output is preserved. `FAIL` outcomes include a direct
remediation; the installer never offers a continue prompt below a hard storage
minimum.

## Models and size probing

The bundled 3B and 7B model URLs use authenticated redirects when `HF_TOKEN` is
set. If HTTP size metadata is unavailable, their verified fallback estimates
are 2 GiB and 5 GiB. Existing partial-file bytes are subtracted.

For a custom model, set a usable `MODEL_URL`. When the server cannot report its
size, also set a whole-number estimate:

```env
MODEL_EXPECTED_SIZE_GB=20
```

The VM60 profile cannot install without either its selected local GGUF file or
a URL. This is checked before build.

## Manual setup

```bash
./ai-stack doctor
./ai-stack init
./ai-stack model download
./ai-stack build
./ai-stack up
./ai-stack status
```

Manual `build` and `up` commands still apply the resolved GPU overlay when
`PYTORCH_BACKEND` is a CUDA backend.

## Rerunning

The installer preserves existing model files and resumes partial downloads.
Configuration is backed up before mutation. Rebuilding is required after a
compute backend change:

```bash
./ai-stack compute cpu
./ai-stack build
./ai-stack up
```

## Related docs

- [Hardware detection](hardware-detection.md)
- [NVIDIA GPU installation](gpu-installation.md)
- [Runtime storage](runtime-storage.md)
- [Troubleshooting](../operations/troubleshooting.md)
