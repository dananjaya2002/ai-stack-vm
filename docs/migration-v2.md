# Migration Guide — Phase 1 → Phase 2 (Unified Memory Layout)

This guide covers migrating from the Phase 1 directory layout to the new Phase 2 unified `memory/` structure.

---

## What Changed

### Directory Layout

| Phase 1 (old)                     | Phase 2 (new)                               |
|-----------------------------------|---------------------------------------------|
| `~/ai-stack/memory/`              | `~/ai-stack/memory/engineering-memory/`     |
| `~/ai-stack/memory/architecture/` | `~/ai-stack/memory/engineering-memory/architecture/` |
| `~/ai-stack/memory/debugging-notes/` | `~/ai-stack/memory/engineering-memory/debugging-notes/` |
| `~/ai-stack/memory/persons/`      | `~/ai-stack/memory/engineering-memory/persons/` |
| `~/ai-stack/repos/`               | `~/ai-stack/memory/code-memory/`            |

### Port Changes

| Service       | Phase 1 | Phase 2 |
|---------------|---------|---------|
| code-proxy    | 8082    | **9001** |
| memory-proxy  | 8081/9000 | **9002** |
| vm-llama      | 8082    | 8082 _(unchanged)_ |

### Env Files Location

Phase 1 may have had env files at various locations. In Phase 2 the canonical locations are:

| File                                            | Purpose                    |
|-------------------------------------------------|----------------------------|
| `scripts/memory-proxy/.example.memory-api.env` | Memory-proxy configuration |
| `scripts/code-proxy/.example.code-proxy.env`   | Code-proxy configuration   |

Your **real** env files (with actual secrets/tokens) should be copies of these at:
- `scripts/memory-proxy/memory-api.env`
- `scripts/code-proxy/code-proxy.env`

---

## Step-by-Step Migration

### Step 1 — Locate your old env files

In Phase 1 the env file was often at one of these locations on the VM:

```bash
# Check common old locations:
ls ~/ai-stack/scripts/memory-api.env
ls ~/ai-stack/memory-api.env
ls ~/ai-stack/scripts/.env
```

Copy whichever exists to the new canonical location:

```bash
cp ~/ai-stack/scripts/memory-api.env ~/ai-stack/scripts/memory-proxy/memory-api.env
```

---

### Step 2 — Move engineering-memory files

```bash
# Create new subdirectory
mkdir -p ~/ai-stack/memory/engineering-memory

# Move all your existing memory files into the new subdirectory
mv ~/ai-stack/memory/architecture  ~/ai-stack/memory/engineering-memory/
mv ~/ai-stack/memory/debugging-notes ~/ai-stack/memory/engineering-memory/
mv ~/ai-stack/memory/persons       ~/ai-stack/memory/engineering-memory/

# Move any loose markdown files too
find ~/ai-stack/memory -maxdepth 1 -name "*.md" -exec mv {} ~/ai-stack/memory/engineering-memory/ \;

# Verify
ls ~/ai-stack/memory/engineering-memory/
```

---

### Step 3 — Move repos into code-memory

```bash
# Create new code-memory subdirectory
mkdir -p ~/ai-stack/memory/code-memory

# Move any existing cloned repos from the old repos/ folder
# (if you had ~/ai-stack/repos/<project>/ entries)
for repo_dir in ~/ai-stack/repos/*/; do
  repo_name=$(basename "$repo_dir")
  echo "Moving $repo_name → memory/code-memory/"
  mv "$repo_dir" ~/ai-stack/memory/code-memory/
done

# Verify
ls ~/ai-stack/memory/code-memory/
```

If `~/ai-stack/repos/` is now empty, remove it:

```bash
rmdir ~/ai-stack/repos  # only works if it is empty
```

---

### Step 4 — Re-index engineering-memory into Qdrant

The old Qdrant vectors reference the old file paths. Re-index to update the path metadata:

```bash
cd ~/ai-stack/repos/ai-stack-vm   # or wherever the repo is checked out

# Activate your Python venv
source ~/ai-stack/python-envs/qdrant-env/bin/activate

# Full re-index of engineering-memory (overwrites stale vectors)
python scripts/memory-proxy/index_memory.py
```

> ℹ️ `index_memory.py` deletes and re-creates vectors per file, so running a full re-index is safe and idempotent.

---

### Step 5 — Re-index code-memory into Qdrant (if you had code repos)

```bash
# Index each repo you moved
python scripts/code-proxy/index_code.py ~/ai-stack/memory/code-memory/<repo-name>
```

---

### Step 6 — Update systemd watcher service

If you had a `memory-watcher.service` pointing to the old path, edit it:

```bash
systemctl --user stop memory-watcher.service
systemctl --user edit --force memory-watcher.service
```

The `ExecStart` line should reference the script, which now internally uses the new path (`engineering-memory`) by default. No change needed if you're running the script directly — the path is already updated in `watch_memory.py`.

---

### Step 7 — Rebuild Docker images

The Dockerfiles changed (new ports: `9001` for code-proxy, `9002` for memory-proxy):

```bash
# Rebuild base image
docker build -f docker/Dockerfile.base -t ai-stack/base-deps .

# Rebuild memory-proxy (now on port 9002)
docker build -f docker/Dockerfile.memory-proxy -t ai-stack/memory-proxy .

# Rebuild code-proxy (now on port 9001)
docker build -f docker/Dockerfile.code-proxy -t ai-stack/code-proxy .
```

---

### Step 8 — Restart all services

```bash
# Stop old containers
podman stop memory-api code-proxy 2>/dev/null || true
docker compose down 2>/dev/null || true

# Start fresh with new compose
docker compose up -d

# Verify
bash health-check.sh
```

---

### Step 9 — Update Continue.dev config (on laptop)

Update `~/.continue/config.yaml` to use the new ports:

```yaml
# memory-proxy: was :9000 or :8081, now :9002
- name: Memory Proxy
  apiBase: http://localhost:9002/v1

# code-proxy: was :8082, now :9001
- name: Code Proxy
  apiBase: http://localhost:9001/v1
```

Then update your OpenShift port-forwards accordingly if you were forwarding the old ports.

---

## Verification Checklist

After migration, verify each component:

```bash
# 1. Engineering-memory files are in the right place
ls ~/ai-stack/memory/engineering-memory/

# 2. Code repos are in the right place
ls ~/ai-stack/memory/code-memory/

# 3. Qdrant is running
curl -s http://localhost:6333/healthz

# 4. Check engineering-memory vectors exist
curl -s http://localhost:6333/collections/engineering-memory | python3 -m json.tool

# 5. Check code-memory vectors exist (if you had repos)
curl -s http://localhost:6333/collections/code-memory | python3 -m json.tool

# 6. Test memory-proxy endpoint
curl -s http://localhost:9002/v1/models

# 7. Test code-proxy endpoint
curl -s http://localhost:9001/v1/models

# 8. Full health check
bash health-check.sh
```

---

## What to NOT Delete Yet

Before you are fully confident the migration worked, keep:
- `~/ai-stack/repos/` — keep until you confirm all repos moved and re-indexed correctly
- Your old `memory-api.env` backup — keep until new env files are confirmed working

Once verified, remove the old folder:

```bash
rm -rf ~/ai-stack/repos   # only after confirming code-memory is working
```
