#!/usr/bin/env bash
set -e

podman rm -f memory-api 2>/dev/null || true

podman run -d \
  --name memory-api \
  --restart=always \
  --network host \
  --env-file ~/ai-stack/scripts/memory-api.env \
  -v ~/ai-stack/repos:/repos:ro \
  -v ~/ai-stack/logs:/logs \
  memory-api:local

echo "memory-api recreated"
podman exec memory-api printenv | grep MEMORY_API_LOGS || true
