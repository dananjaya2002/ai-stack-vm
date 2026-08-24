# Installation

This guide installs AI Stack VM, starts the core services, and verifies the
local model and retrieval stack.

## Prerequisites

Use a Linux host with:

- Docker Engine and the Docker Compose plugin
- `git`, `curl`, and `awk`
- Enough free space for the selected GGUF model and container images
- Optional NVIDIA GPU, driver, and container toolkit for GPU mode

Podman is supported for CPU installations. GPU mode requires Docker and a
working NVIDIA container runtime.

Check the host before installing:

```bash
git --version
curl --version
docker --version
docker compose version
```

## Clone the project

```bash
git clone https://github.com/dananjaya2002/ai-stack-vm.git
cd ai-stack-vm
chmod +x ./ai-stack
```

## Run the installer

Automatic compute selection is recommended:

```bash
./ai-stack install --compute auto
```

To force a specific mode:

```bash
./ai-stack install --compute cpu
./ai-stack install --compute gpu
```

- `auto` selects GPU mode only when every NVIDIA host and container check
  succeeds; otherwise it uses CPU mode.
- `cpu` provides the most portable installation and smallest images.
- `gpu` requires a working NVIDIA environment and stops if validation fails.

During installation, select one of the listed models or choose the custom-model
option and provide a direct URL to a llama.cpp-compatible GGUF file. The
installer checks the host, prepares configuration, downloads the model, builds
the required images, starts the stack, and verifies inference and embeddings.

Existing `.env` configuration is backed up before it is changed. Existing
model downloads are preserved and partial downloads are resumed.

## Open the services

When installation completes, open Open WebUI at `http://localhost:8080`.

Start the optional management dashboard:

```bash
./ai-stack dashboard
```

Then open `http://localhost:9100`.

Use the dashboard to monitor services, upload Markdown notes, manage code
repositories, run indexing, and control automatic watchers.

![Repository management in the AI Stack VM dashboard](../media/repository-managment.png)

The complete interface and installation flow are shown in the
[project demo video](https://kavishanportfolio.vercel.app/?project=ai-stack-vm#projects).

## Verify the installation

```bash
./ai-stack status
./ai-stack doctor
```

## Change compute mode

Changing the embedding backend requires rebuilding and restarting the stack:

```bash
./ai-stack compute cpu
./ai-stack build
./ai-stack up
```

Use `./ai-stack compute gpu` instead when the NVIDIA prerequisites are ready.

## Stop the stack

```bash
./ai-stack down
```

## Next steps

- [Configuration](configuration.md)
- [NVIDIA GPU installation](gpu-installation.md)
- [Runtime storage](runtime-storage.md)
- [CLI reference](../cli/ai-stack.md)
- [Indexing](../operations/indexing.md)
- [Production hardening](../security/production-hardening.md)
- [Troubleshooting](../operations/troubleshooting.md)
