# Hardware Detection and Compute Resolution

Run the read-only report at any time:

```bash
./ai-stack hardware
./ai-stack compute status
./ai-stack doctor
```

The report includes OS and architecture, CPU cores, total/available RAM,
runtime and container storage roots/free space, engine/Compose availability,
service ports, GPU name/VRAM, NVIDIA driver, reported CUDA compatibility,
runtime registration, and container GPU visibility.

To keep this reporting command configuration-safe, it uses the probe image only
when `ubuntu:24.04` is already cached. The installer and `compute auto|gpu`
commands may pull that image when missing because GPU eligibility requires an
actual container probe.

## Compute modes

| Mode | Behavior |
|---|---|
| `cpu` | Never probes or grants GPU access. Uses CPU Torch and CPU embeddings. |
| `auto` | Uses GPU only after every required check succeeds; otherwise explains CPU fallback. |
| `gpu` | Requires every GPU prerequisite and stops with remediation on failure. |

The authoritative matrix is `config/pytorch-backends.conf`. PyTorch is pinned
there rather than in `.env`. For auto mode, the highest matrix backend whose
minimum CUDA value is less than or equal to the `nvidia-smi` compatibility
value is selected.

CUDA compatibility is the maximum CUDA runtime level supported by the installed
driver; it is not the same thing as requiring a host CUDA toolkit installation.
The selected PyTorch wheel brings its required runtime libraries.

## Storage calculation

Runtime and container storage may reside on separate filesystems. When they
share a device, model and image headroom are summed so the same free bytes are
not counted twice. See [Runtime storage](runtime-storage.md) for thresholds.
