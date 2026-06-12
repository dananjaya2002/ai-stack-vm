# AI Stack VM — Private Local RAG System

A self-hosted, private AI assistant platform running across a laptop GPU and a VM (OpenShift/KubeVirt).
Provides repo-aware code generation, long-term memory via Qdrant, and OpenAI-compatible endpoints for Continue.dev and Open WebUI.

---

## Architecture

```
Laptop
├── Docker / NVIDIA RTX 3050 GPU
├── llama.cpp CUDA server         → qwen2.5-coder-3B  @ localhost:8081
└── Continue.dev (VS Code)

VM (OpenShift / KubeVirt)
├── Podman
├── llama.cpp CPU server          → qwen2.5-coder-7B  @ localhost:8082  (vm-llama)
├── Qdrant vector database        →                    @ localhost:6333
├── memory-proxy (FastAPI / RAG)  →                    @ localhost:9002  ← engineering-memory
├── code-proxy   (FastAPI / RAG)  →                    @ localhost:9001  ← code-memory
└── Open WebUI                   →                    @ localhost:8080
```

### Memory directory layout (on VM)

```
~/ai-stack/memory/
├── engineering-memory/     ← markdown notes, architecture docs, personas
│   ├── architecture/
│   ├── debugging-notes/
│   └── persons/
└── code-memory/            ← synced/cloned project repos for code RAG
    ├── my-project/
    └── another-repo/
```

### Request flow

```
User prompt
    ↓
memory-proxy / code-proxy
    ↓  embed query
Qdrant (retrieves relevant chunks)
    ↓  build enriched prompt
llama.cpp VM model (qwen2.5-coder-7B @ :8082)
    ↓
Response → Open WebUI / Continue.dev
```

---

## Port Reference

| Service           | Port  | Notes                              |
|-------------------|-------|------------------------------------|
| laptop-llama      | 8081  | GPU fast coder (3B)                |
| vm-llama          | 8082  | VM deep coder (7B)                 |
| Qdrant REST       | 6333  | Vector database                    |
| Qdrant gRPC       | 6334  | Vector database (gRPC)             |
| Open WebUI        | 8080  | Browser chat UI                    |
| **code-proxy**    | 9001  | Code-RAG OpenAI-compatible proxy   |
| **memory-proxy**  | 9002  | Memory-RAG OpenAI-compatible proxy |

---

## Prerequisites

- VM: Podman installed and running
- Laptop: Docker + NVIDIA Container Toolkit
- Python 3.11+ for local scripts (optional)
- OpenShift `oc` CLI (for port-forwarding from VM)

---

## Setup

### 1. Clone and prepare folders (on VM)

```bash
mkdir -p ~/ai-stack/{open-webui,qdrant,python-envs,logs,backups}
mkdir -p ~/ai-stack/memory/engineering-memory/{architecture,debugging-notes,persons}
mkdir -p ~/ai-stack/memory/code-memory
git clone <repo-url> ~/ai-stack/repos/ai-stack-vm
```

### 2. Copy env files and fill in values

```bash
cp scripts/.example.memory-api.env scripts/memory-api.env
cp scripts/.example.code-proxy.env scripts/code-proxy.env
# Edit each file with real values (LLM_BASE_URL, Qdrant settings, etc.)
nano scripts/memory-api.env
nano scripts/code-proxy.env
```

### 3. Build Docker images

```bash
# Build shared base image first
docker build -f docker/Dockerfile.base -t ai-stack/base-deps .

# Build memory-proxy image
docker build -f docker/Dockerfile.memory-proxy -t ai-stack/memory-proxy .

# Build code-proxy image
docker build -f docker/Dockerfile.code-proxy -t ai-stack/code-proxy .
```

---

## Running Services

### Option A — Run everything together (master compose)

```bash
# Start Qdrant + memory-proxy + code-proxy
docker compose up -d

# Stop all
docker compose down

# View logs
docker compose logs -f
```

### Option B — Run services independently

```bash
# Qdrant + memory-proxy only
docker compose -f docker-compose.memory-proxy.yml up -d

# Qdrant + code-proxy only
docker compose -f docker-compose.code-proxy.yml up -d
```

### vm-llama (Podman on VM)

```bash
# Start vm-llama (should be managed by systemd, see below)
podman start vm-llama

# Check status
podman ps

# Logs
podman logs -f vm-llama
```

### Laptop GPU model

```bash
# Start laptop-llama container (run on your laptop)
docker start laptop-llama

# Logs
docker logs -f laptop-llama
```

---

## systemd Services (VM)

The VM model is managed as a systemd user service so it auto-starts on boot.

```bash
# Check status
systemctl --user status container-vm-llama.service

# Start / stop / restart
systemctl --user start  container-vm-llama.service
systemctl --user stop   container-vm-llama.service
systemctl --user restart container-vm-llama.service

# Enable auto-start on boot
systemctl --user enable container-vm-llama.service
```

For the memory file auto-indexing watcher:

```bash
systemctl --user status  memory-watcher.service
systemctl --user start   memory-watcher.service
systemctl --user enable  memory-watcher.service
```

---

## OpenShift Port Forwarding

To access the VM model from your laptop:

```bash
oc port-forward pod/virt-launcher-vm-ai-<pod-id> 8082:8082
```

This makes `http://localhost:8082/v1` available on the laptop, pointing to the VM's llama.cpp server.

---

## Memory System

### Index memory files manually

```bash
# Index all engineering-memory files
python scripts/memory-proxy/index_memory.py

# Index a single file (incremental)
python scripts/memory-proxy/index_memory.py ~/ai-stack/memory/engineering-memory/persons/my-note.md
```

### Search memory (debug)

```bash
python scripts/memory-proxy/search_memory.py
```

### Run memory watcher (auto-index on file save)

```bash
# Watches ~/ai-stack/memory/engineering-memory/ and re-indexes any file that changes
python scripts/memory-proxy/watch_memory.py
```

> ℹ️ The `memory-proxy` container does **not** run the watcher. Run `watch_memory.py` separately or use the `memory-watcher.service` systemd unit.

### Ask a question via memory RAG (CLI)

```bash
python scripts/memory-proxy/ask_with_memory.py
```

---

## Code Memory System

### Index a project repo

```bash
# Clone/copy your project into code-memory first
git clone <project-url> ~/ai-stack/memory/code-memory/<repo-name>
# or rsync from laptop:
rsync -av /path/to/local/project/ vm-host:~/ai-stack/memory/code-memory/<repo-name>/

# Then index it into Qdrant
python scripts/code-proxy/index_code.py ~/ai-stack/memory/code-memory/<repo-name>
```

### Index a specific file
```bash
python scripts/code-proxy/index_code.py ~/ai-stack/memory/code-memory/<repo-name>/src/main.py
```

### Search code chunks (debug)

```bash
python scripts/code-proxy/search_code.py
```

### Run code watcher (auto-index on save)

```bash
python scripts/code-proxy/watch_code.py ~/ai-stack/memory/code-memory
```

---

## Health Check

```bash
bash health-check.sh
```

Checks:
- vm-llama health endpoint (`:8082`)
- vm-llama models endpoint
- Open WebUI availability
- Running Podman containers
- systemd user service status

---

## Logs

### View memory-proxy logs

```bash
python scripts/view_logs.py
# Reads ~/ai-stack/logs/memory_api.log
# Offers option to delete after viewing
```

### Tail logs directly

```bash
tail -f ~/ai-stack/logs/memory_api.log
tail -f ~/ai-stack/logs/code_proxy.log
```

### Docker Compose logs

```bash
docker compose logs -f memory-proxy
docker compose logs -f code-proxy
docker compose logs -f qdrant
```

---

## Backup

```bash
bash backup-ai-stack.sh
```

Backs up (to `~/ai-stack/backups/`):
- Open WebUI data
- Qdrant vector data
- Scripts and config files
- Env files
- Logs
- systemd / Podman container config

> Backups older than 7 days are pruned automatically.

---

## Continue.dev Config

Add these models to your `~/.continue/config.yaml` on the laptop:

```yaml
models:
  - name: Laptop Fast Coder
    provider: openai
    model: qwen2.5-coder-3b
    apiBase: http://localhost:8081/v1
    apiKey: dummy
    roles: [chat, edit, apply]

  - name: VM Deep Coder
    provider: openai
    model: qwen2.5-coder-7b
    apiBase: http://localhost:8082/v1
    apiKey: dummy
    roles: [chat, edit, apply]

  - name: Memory Proxy
    provider: openai
    model: memory-proxy
    apiBase: http://localhost:9002/v1
    apiKey: dummy
    roles: [chat]

  - name: Code Proxy
    provider: openai
    model: code-proxy
    apiBase: http://localhost:9001/v1
    apiKey: dummy
    roles: [chat]

  - name: Local Embeddings
    provider: transformers.js
    model: all-MiniLM-L6-v2
    roles: [embed]
```

---

## Repository Layout

```
ai-stack-vm/
├── code-proxy/              # code-proxy standalone source
│   ├── code_proxy.py
│   ├── index_code.py
│   ├── search_code.py
│   ├── watch_code.py
│   ├── Dockerfile
│   └── .example.code-proxy.env
├── docker/                  # Dockerfiles for VM containers
│   ├── Dockerfile.base
│   ├── Dockerfile.memory-proxy
│   └── Dockerfile.code-proxy
├── scripts/                 # All Python scripts + env examples
│   ├── memory_api.py
│   ├── code_proxy.py
│   ├── index_memory.py
│   ├── index_code.py
│   ├── search_memory.py
│   ├── watch_memory.py
│   ├── watch_code.py
│   ├── ask_with_memory.py
│   ├── view_logs.py
│   ├── ask.sh
│   ├── .example.memory-api.env
│   └── .example.code-proxy.env
├── docs/
│   ├── ports.md
│   ├── migration-v2.md
│   └── project-phase-1.md
├── docker-compose.yml               # Master: all services
├── docker-compose.memory-proxy.yml  # Memory-proxy + Qdrant only
├── docker-compose.code-proxy.yml    # Code-proxy + Qdrant only
├── health-check.sh
├── backup-ai-stack.sh
└── requirements.txt
```

---

## What is NOT committed to Git

```
models/          ← GGUF model files (too large)
qdrant/          ← Vector database storage
open-webui/      ← Open WebUI chat history/data
python-envs/     ← Python virtual environments
logs/            ← Runtime logs
backups/         ← Backup archives
*.env            ← Real env files with secrets
```

> **Note:** The `~/ai-stack/memory/` directory on the VM is **not** part of this repo.
> It lives only on the VM and contains your personal engineering notes and cloned code repos.
> Back it up with `backup-ai-stack.sh`.
