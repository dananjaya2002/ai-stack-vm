# AI Stack Project Summary

## 1. Overall Goal

We built a local/private AI assistant system using:

- A **laptop GPU** for fast coding assistance.
- A **VM running on OpenShift/KubeVirt** for deeper model inference and persistent AI services.
- **Continue.dev** inside VS Code.
- **Open WebUI** as a browser-based chat interface.
- **Qdrant** as long-term vector memory.
- A custom **Memory API** exposing an OpenAI-compatible endpoint and injecting Qdrant memory into prompts.

Final architecture:

```text
Laptop
├── Docker
├── NVIDIA RTX 3050 GPU
├── llama.cpp CUDA server
├── qwen2.5-coder-3B
├── Continue.dev
└── Fast coding endpoint on localhost:8081

VM
├── Podman
├── llama.cpp CPU server
├── qwen2.5-coder-7B
├── Open WebUI
├── Qdrant vector database
├── memory_api container
├── memory indexing scripts
├── debug/log viewer
└── Memory/RAG endpoint on localhost:9000
```

---

## 2. Laptop GPU Model Setup

### 2.1 GPU Container Test

You verified Docker GPU access with:

```bash
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
```

The output showed:

```text
NVIDIA GeForce RTX 3050 Laptop GPU
6144 MiB VRAM
```

This confirmed:

```text
✅ Docker GPU passthrough works
✅ NVIDIA Container Toolkit works
✅ RTX 3050 is visible inside containers
```

### 2.2 Laptop llama.cpp Container

The laptop model file:

```text
/ai-stack/models/qwen2.5-coder-3b-instruct-q4_k_m.gguf
```

The laptop endpoint became:

```text
http://localhost:8081/v1
```

The container name:

```text
laptop-llama
```

Confirmed model:

```text
qwen2.5-coder-3b-instruct-q4_k_m.gguf
```

Performance:

```text
~68 tokens/sec
```

Role:

```text
Laptop Fast Coder
```

Best for:

```text
- quick coding help
- small code explanations
- simple functions
- quick fixes
- small refactors
```

---

## 3. VM llama.cpp Model Setup

### 3.1 Clean Podman Reset

Fresh folders were created:

```bash
mkdir -p ~/ai-stack/{models,open-webui,qdrant,repos,scripts}
```

Verified:

```text
✅ No containers
✅ No images
✅ No volumes
✅ Fresh ai-stack folders
```

### 3.2 VM llama.cpp CPU Server

The VM model:

```text
qwen2.5-coder-7b-instruct-q4_k_m.gguf
```

Endpoint:

```text
http://localhost:8082/v1
```

Container:

```text
vm-llama
```

Port mapping:

```text
0.0.0.0:8082 -> 8080/tcp
```

Performance:

```text
~34 tokens/sec
```

Role:

```text
VM Deep Coder
```

Best for:

```text
- deeper reasoning
- architecture analysis
- larger explanations
- code review
- repo-level reasoning
```

### 3.3 VM Model systemd Service

Created service:

```text
container-vm-llama.service
```

Confirmed:

```text
Active: active (running)
server is listening on http://0.0.0.0:8080
```

---

## 4. OpenShift / Port Forwarding / Route Setup

### 4.1 Port Forwarding

Used OpenShift port forwarding:

```bash
oc port-forward pod/virt-launcher-vm-ai-xqwrl 8082:8082
```

This made the VM model reachable from the laptop:

```text
http://localhost:8082/v1
```

### 4.2 Open WebUI Route

Open WebUI was exposed through OpenShift Service and Route.

Example route:

```text
http://route-ollama-server-dep-of-agrarian-dev.apps.sovecloud.akaza.lk/
```

We resolved networking issues around:

```text
host.containers.internal
127.0.0.1
port 3000 vs 8080
container network vs host network
```

Important principle:

```text
127.0.0.1 inside a container != VM host
```

---

## 5. Continue.dev Setup

### 5.1 Initial Config Fix

Continue required `name`, not `title`.

Working base config:

```yaml
name: Local Config
version: 1.0.0
schema: v1

models:
  - name: Laptop Fast Coder
    provider: openai
    model: qwen2.5-coder-3b
    apiBase: http://localhost:8081/v1
    apiKey: dummy
    roles:
      - chat
      - edit
      - apply

  - name: VM Deep Coder
    provider: openai
    model: qwen2.5-coder-7b
    apiBase: http://localhost:8082/v1
    apiKey: dummy
    roles:
      - chat
      - edit
      - apply
```

### 5.2 Repo-Aware Continue Config

Added local embeddings and context providers:

```yaml
  - name: Local Embeddings
    provider: transformers.js
    model: all-MiniLM-L6-v2
    roles:
      - embed

context:
  - provider: currentFile
  - provider: file
  - provider: code
  - provider: folder
  - provider: codebase
  - provider: diff
  - provider: terminal
  - provider: open
```

Removed problematic entries:

```text
autocomplete
problems
```

Stable context tools:

```text
✅ @currentFile
✅ @file
✅ @code
✅ @folder
✅ @codebase
✅ @diff
✅ @terminal
✅ @open
```

---

## 6. Open WebUI Setup

Open WebUI was deployed with Podman and connected successfully to the VM model endpoint.

It is used for:

```text
- longer conversations
- saved chats
- model endpoint testing
- memory-proxy usage
- future code-memory-proxy usage
```

---

## 7. Qdrant Setup

### 7.1 Running Qdrant

Started Qdrant with Podman:

```bash
podman run -d \
  --name qdrant \
  --restart=always \
  -p 6333:6333 \
  -p 6334:6334 \
  -v ~/ai-stack/qdrant:/qdrant/storage:z \
  docker.io/qdrant/qdrant
```

Needed full image path:

```text
docker.io/qdrant/qdrant
```

because Podman did not resolve the short image name.

Health check:

```bash
curl http://localhost:6333/healthz
```

Output:

```text
healthz check passed
```

---

## 8. Python Virtual Environment

Created isolated Python environment:

```text
~/ai-stack/python-envs/qdrant-env
```

Installed packages:

```bash
pip install qdrant-client sentence-transformers tqdm watchdog fastapi uvicorn requests
```

Used for:

```text
- indexing scripts
- search scripts
- watcher script
- local debugging
```

The venv is **not committed to Git**.

---

## 9. Engineering Memory / RAG System

### 9.1 Memory Folder

Created:

```text
~/ai-stack/memory/
```

With subfolders:

```text
memory/
├── architecture/
├── debugging-notes/
├── persons/
└── test.md
```

Example memory file:

```text
~/ai-stack/memory/persons/Dr_Necremeton_Persona.md
```

### 9.2 `index_memory.py`

Purpose:

```text
1. Read memory files
2. Split into chunks
3. Convert chunks to embeddings using all-MiniLM-L6-v2
4. Store vectors in Qdrant collection engineering-memory
5. Add metadata:
   - file
   - chunk_index
   - category
   - text
```

Supports incremental indexing:

```bash
python index_memory.py /path/to/single-file.md
```

### 9.3 `search_memory.py`

Debug tool for querying Qdrant manually.

Example:

```bash
python search_memory.py
```

Query:

```text
Necremeton
```

Confirmed retrieval from:

```text
Dr_Necremeton_Persona.md
```

### 9.4 `ask_with_memory.py`

CLI RAG tool:

```text
1. Accept question
2. Search Qdrant memory
3. Build prompt with retrieved memory
4. Call llama.cpp
5. Return answer
```

---

## 10. Auto-Indexing and Incremental Indexing

### 10.1 `watch_memory.py`

Purpose:

```text
Watch ~/ai-stack/memory for changes
Wait for changes to settle
Call index_memory.py only for the changed file
```

Flow:

```text
Edit memory file
    ↓
watch_memory.py detects change
    ↓
waits 5 seconds
    ↓
calls index_memory.py changed-file.md
    ↓
Qdrant is updated
```

### 10.2 Debounce / Settle Behavior

Added:

```text
Edit → wait 5 seconds → index once
```

This prevents repeated indexing loops.

### 10.3 Incremental Indexing

Before:

```text
Edit one file → re-index everything
```

Now:

```text
Edit one file → only that file is re-indexed
```

### 10.4 Runtime Note

The `memory-api` Podman container runs only:

```text
memory_api.py
```

It does **not** run:

```text
watch_memory.py
```

So `watch_memory.py` must run separately, ideally as:

```text
memory-watcher.service
```

---

## 11. Memory API

### 11.1 `memory_api.py`

FastAPI service exposing:

```text
GET  /v1/models
POST /v1/chat/completions
POST /ask
POST /search
```

### 11.2 Flow

```text
User prompt
    ↓
memory_api.py
    ↓
embed query
    ↓
search Qdrant
    ↓
filter relevant chunks
    ↓
build prompt
    ↓
call llama.cpp at localhost:8082/v1/chat/completions
    ↓
return OpenAI-compatible response
```

### 11.3 `memory-proxy`

Virtual model exposed by `/v1/models`:

```text
memory-proxy
```

It represents:

```text
Qdrant memory + llama.cpp model
```

---

## 12. Smart Retrieval Improvements

### 12.1 Relevance Threshold

Added:

```python
SCORE_THRESHOLD = 0.5
```

Purpose:

```text
Avoid injecting unrelated memory
```

### 12.2 Multi-Chunk Retrieval

Improved from:

```text
1 file → 1 chunk
```

to:

```text
1 file → best 2 chunks
```

### 12.3 Categories

`index_memory.py` stores:

```python
"category": file_path.parent.name
```

Example:

```text
memory/persons/Dr_Necremeton_Persona.md
```

gets:

```json
"category": "persons"
```

### 12.4 Debug Logs

Optional logs:

```text
search_query
chunk_seen
chunk_selected
final_context
prompt_built
model_response
```

---

## 13. Logging System

### 13.1 Toggle

```python
ENABLE_LOGGING = os.getenv("MEMORY_API_LOGS", "false").lower() == "true"
```

Logs collect only when:

```env
MEMORY_API_LOGS=true
```

### 13.2 Configurable Log File

```python
LOG_FILE = Path(os.getenv("MEMORY_API_LOG_FILE", "/tmp/memory_api.log"))
```

Container log path:

```text
/logs/memory_api.log
```

Host path:

```text
~/ai-stack/logs/memory_api.log
```

Mount:

```bash
-v ~/ai-stack/logs:/logs
```

### 13.3 `view_logs.py`

Reads:

```text
~/ai-stack/logs/memory_api.log
```

Formats logs and asks:

```text
Delete logs? [y/no]
```

---

## 14. Containerizing Memory API

### 14.1 Renamed Files

Renamed to underscores:

```text
ask_with_memory.py
index_memory.py
memory_api.py
search_memory.py
view_logs.py
watch_memory.py
```

### 14.2 Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 9000

CMD ["uvicorn", "memory_api:app", "--host", "0.0.0.0", "--port", "9000"]
```

### 14.3 requirements.txt

Includes:

```text
fastapi
uvicorn
pydantic
qdrant-client
sentence-transformers
requests
tqdm
watchdog
```

### 14.4 Running Container

```bash
podman run -d \
  --name memory-api \
  --restart=always \
  --network host \
  --env-file ~/ai-stack/scripts/memory-api.env \
  -v ~/ai-stack/repos:/repos:ro \
  -v ~/ai-stack/logs:/logs \
  memory-api:local
```

Confirmed answer to:

```text
Who is Dr Necremeton?
```

using Qdrant memory.

---

## 15. Environment File

Example:

```env
MEMORY_API_LOGS=true
MEMORY_API_LOG_FILE=/logs/memory_api.log

QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_COLLECTION=engineering-memory

LLM_BASE_URL=http://localhost:8082/v1
LLM_MODEL=qwen2.5-coder-7b-instruct-q4_k_m.gguf

MEMORY_TOP_K=5
MEMORY_SCORE_THRESHOLD=0.5
```

Important security note:

```text
Any exposed HF_TOKEN should be revoked/regenerated.
```

---

## 16. GitHub / Repo Organization

Prepared structure:

```text
ai-stack/
├── scripts/
├── VM-related/
├── models/
├── qdrant/
├── open-webui/
├── python-envs/
├── logs/
├── backups/
└── repos/
```

README placeholder files keep ignored folders visible:

```text
models/README.md
qdrant/README.md
python-envs/README.md
open-webui/README.md
```

Recommended `.gitignore` patterns:

```gitignore
models/*
!models/README.md

qdrant/*
!qdrant/README.md

python-envs/*
!python-envs/README.md

open-webui/*
!open-webui/README.md

logs/
backups/
*.env
!.example.memory-api.env
```

---

## 17. Backup Script

Initial backup covered:

```text
open-webui
qdrant
systemd user units
```

Recommended additions:

```text
scripts/
VM-related/
memory-api.env
logs/
systemd/containers config
backup pruning
```

---

## 18. Current Runtime Architecture

```text
Memory files
   ↓
watch_memory.py  [host service, separate from container]
   ↓
index_memory.py
   ↓
Qdrant
   ↓
memory_api container
   ↓
llama.cpp VM model
   ↓
Open WebUI / Continue
```

The memory API container itself does **not** auto-index files.

Auto-indexing requires:

```text
watch_memory.py running separately
```

---

## 19. Current Limitations

### 19.1 Project code is not yet indexed

Qdrant currently mainly has:

```text
engineering-memory
```

which includes memory markdown/text files.

It does not yet automatically contain laptop project source code.

### 19.2 Continue `@codebase` is separate

Continue has its own codebase context. It is separate from Qdrant.

---

## 20. Planned Next Upgrade: `code-memory-proxy`

Goal:

```text
code-memory-proxy
```

Separate Qdrant collection:

```text
code-memory
```

Planned flow:

```text
Laptop project files
    ↓
sync/clone/copy to VM
    ↓
~/ai-stack/repos/<project-name>
    ↓
index_code.py
    ↓
Qdrant collection: code-memory
    ↓
code-memory-proxy
    ↓
Continue/Open WebUI
```

Each code chunk should include metadata:

```json
{
  "repo": "project-name",
  "file": "/path/to/file",
  "relative_path": "src/auth/login.ts",
  "language": "typescript",
  "category": "code",
  "chunk_index": 0,
  "text": "..."
}
```

---

## 21. Key Concepts Clarified

### 21.1 RAG vs Conversation Compaction

What was built:

```text
RAG — Retrieval-Augmented Generation
```

Not exactly conversation compaction.

Conversation compaction means summarizing chat history.

Your system does:

```text
files → embeddings → Qdrant → retrieved context → model answer
```

### 21.2 Memory Types

```text
Open WebUI chat context
→ short-term conversation context

Qdrant memory
→ long-term external knowledge from indexed files
```

### 21.3 Qdrant does not index by itself

Qdrant is only the vector database.

Your scripts do the indexing:

```text
index_memory.py writes to Qdrant
search_memory.py searches Qdrant
memory_api.py retrieves from Qdrant during chat
watch_memory.py triggers indexing automatically
```

---

## 22. Current Working Endpoints

```text
Laptop llama.cpp 3B:
http://localhost:8081/v1

VM llama.cpp 7B:
http://localhost:8082/v1

Qdrant:
http://localhost:6333

Memory API:
http://localhost:9000/v1
```

---

## 23. Confirmed Working

```text
✅ Laptop GPU inference works
✅ VM CPU inference works
✅ Continue.dev works
✅ Open WebUI works
✅ Qdrant works
✅ memory_api works
✅ memory-proxy works
✅ Dr Necremeton memory retrieval works
✅ multi-chunk retrieval works
✅ logging works
✅ containerized memory-api works
✅ logs are visible through mounted /logs
✅ project repo structure is being prepared
```

---

## 24. Recommended Next Steps

### Step 1 — Make watcher persistent

Create and enable:

```text
memory-watcher.service
```

### Step 2 — Finalize GitHub repo

Commit:

```text
scripts/
VM-related/
README.md
placeholder READMEs
.gitignore
Dockerfile
requirements.txt
.example.memory-api.env
```

Do not commit:

```text
models/
qdrant data
open-webui data
python-envs/
logs/
backups/
real .env files
tokens
```

### Step 3 — Build `code-memory-proxy`

Create:

```text
index_code.py
search_code.py
code-memory collection
code-memory-proxy virtual model
```

### Step 4 — Project sync/indexing

Decide how laptop projects get to VM:

```text
Git clone
rsync/scp
archive upload
future upload API
```

### Step 5 — Add project-specific code memory

Use metadata:

```text
repo/project name
language
relative path
file path
chunk index
```

### Step 6 — Add `deep-code-rag`

Later combine:

```text
engineering-memory + code-memory
```

for architecture-aware code generation.

---

## 25. Short Final Summary

We built a distributed private AI assistant platform:

```text
Laptop GPU model for fast coding
VM CPU model for deeper reasoning
Open WebUI for browser chat
Continue.dev for VS Code integration
Qdrant for long-term memory
memory_api as an OpenAI-compatible RAG proxy
auto-indexing and incremental indexing for memory files
containerized memory API with Podman
debug logs and log viewer
GitHub-ready repo structure
```

The working RAG path is:

```text
User prompt
    ↓
memory-proxy
    ↓
Qdrant retrieves relevant memory chunks
    ↓
memory_api builds enhanced prompt
    ↓
llama.cpp generates final response
    ↓
Open WebUI / Continue shows answer
```

The next major capability is:

```text
code-memory-proxy
```

which will index project source code into Qdrant so your assistant can retrieve relevant code chunks and help generate project-specific code changes more accurately.
