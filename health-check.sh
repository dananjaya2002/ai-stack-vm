#!/usr/bin/env bash

echo "=== VM AI Health Check ==="
echo

echo "[1] llama.cpp health:"
curl -s http://localhost:8082/health || echo "FAILED"

echo
echo "[2] llama.cpp models:"
curl -s http://localhost:8082/v1/models || echo "FAILED"

echo
echo
echo "[3] Open WebUI:"
curl -s -I http://localhost:8080 | head -n 1 || echo "FAILED"

echo
echo "[4] Podman containers:"
podman ps

echo
echo "[5] systemd user services:"
systemctl --user --no-pager status container-vm-llama.service | head -n 12 || true
systemctl --user --no-pager status open-webui.service | head -n 12 || true
