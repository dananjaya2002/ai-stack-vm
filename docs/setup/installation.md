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
4. Recommend and select a bundled GGUF model, configure the high-resource
   preset, or add a custom GGUF model.
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

The high-resource preset asks for its direct GGUF URL because the project does
not bundle a stable download location for it. The custom option also collects
the model name, filename, runtime profile, optional size estimate, and optional
SHA-256 checksum. The selection is used for storage validation and then written
to `.env` before download.

## Add a custom model

Run the interactive model installer and enter a model name plus a direct URL to
a single GGUF file:

```bash
./ai-stack model add
```

The wizard derives the filename, accepts an optional size estimate and SHA-256
checksum, downloads the file with resume support, and activates it in `.env`.
It supports GGUF models compatible with llama.cpp; it does not convert model
formats or combine split GGUF files. To script the operation:

```bash
./ai-stack model add \
  --name Qwen3-8B-Q4_K_M \
  --url https://example.invalid/models/Qwen3-8B-Q4_K_M.gguf \
  --profile vm16 \
  --size-gb 6 \
  --yes
```

If the stack is already running, load the new model with:

```bash
./ai-stack apply-config
```

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
