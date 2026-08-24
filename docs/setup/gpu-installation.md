# NVIDIA GPU Installation

GPU embeddings require Linux x86_64, Docker with the Compose plugin, a working
NVIDIA driver and `nvidia-smi`, NVIDIA Container Toolkit runtime access, and a
successful container probe. Podman is supported for CPU mode only in this
release.

## Verify the host

Follow the [NVIDIA Container Toolkit installation guide](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html),
then verify:

```bash
nvidia-smi
docker info
./ai-stack hardware
```

The CLI uses the documented NVIDIA sample-workload pattern with
`ubuntu:24.04`, `--gpus all`, and pull-if-missing behavior. This verifies actual
container visibility instead of trusting runtime configuration alone.

## Select GPU compute

```bash
./ai-stack compute gpu
./ai-stack build
./ai-stack up
```

Or perform the complete installation:

```bash
./ai-stack install --compute gpu
```

The generated Compose configuration uses [Docker Compose GPU device
reservations](https://docs.docker.com/compose/how-tos/gpu-support/). GPU access
is limited to memory/code RAG, dashboard/indexer, and Agentic RAG. It is not
granted to Qdrant, Open WebUI, or `vm-llama`.

## Backend mapping

PyTorch 2.12.1 uses the official CPU, CUDA 12.6, CUDA 13.0, and CUDA 13.2 wheel
indexes listed by [PyTorch previous versions](https://pytorch.org/get-started/previous-versions/).
For example, a driver reporting CUDA 13.1 selects `cu130`; 13.2 or newer selects
`cu132`.

## Failure behavior

- `auto` records `cpu` plus an explanation when GPU verification is uncertain.
- `gpu` exits before model download/build and prints the failed prerequisite.
- A CUDA-configured stack refuses a Podman or legacy `docker-compose` path.
- Post-start verification checks CUDA wheel identity, `torch.cuda`, device name,
  configured embedding device, and a test embedding.
