#!/usr/bin/env bash
set -e

AI_STACK_DIR="$HOME/ai-stack"
BACKUP_DIR="$AI_STACK_DIR/backups"
DATE=$(date +"%Y-%m-%d_%H-%M-%S")

mkdir -p "$BACKUP_DIR"

echo "=== AI Stack Backup Started: $DATE ==="

echo
echo "Backing up Open WebUI data..."
if [ -d "$AI_STACK_DIR/open-webui" ]; then
  tar -czf "$BACKUP_DIR/open-webui-$DATE.tar.gz" -C "$AI_STACK_DIR" open-webui || true
else
  echo "Open WebUI directory not found, skipping."
fi

echo
echo "Backing up Qdrant data..."
if [ -d "$AI_STACK_DIR/qdrant" ]; then
  tar -czf "$BACKUP_DIR/qdrant-$DATE.tar.gz" -C "$AI_STACK_DIR" qdrant || true
else
  echo "Qdrant directory not found, skipping."
fi

echo
echo "Backing up scripts and configuration..."
tar -czf "$BACKUP_DIR/scripts-config-$DATE.tar.gz" \
  -C "$AI_STACK_DIR" \
  scripts \
  VM-related \
  .gitignore \
  README.md \
  2>/dev/null || true

echo
echo "Backing up memory API env file..."
if [ -f "$AI_STACK_DIR/scripts/memory-api.env" ]; then
  tar -czf "$BACKUP_DIR/memory-api-env-$DATE.tar.gz" -C "$AI_STACK_DIR/scripts" memory-api.env || true
elif [ -f "$AI_STACK_DIR/memory-api.env" ]; then
  tar -czf "$BACKUP_DIR/memory-api-env-$DATE.tar.gz" -C "$AI_STACK_DIR" memory-api.env || true
else
  echo "memory-api.env not found, skipping."
fi

echo
echo "Backing up logs if exists..."
if [ -d "$AI_STACK_DIR/logs" ]; then
  tar -czf "$BACKUP_DIR/logs-$DATE.tar.gz" -C "$AI_STACK_DIR" logs || true
else
  echo "Logs directory not found, skipping."
fi

echo
echo "Backing up systemd and container config..."
if [ -d "$HOME/.config/systemd" ] || [ -d "$HOME/.config/containers" ]; then
  tar -czf "$BACKUP_DIR/systemd-containers-$DATE.tar.gz" \
    -C "$HOME/.config" \
    systemd \
    containers \
    2>/dev/null || true
else
  echo "No systemd/containers config found, skipping."
fi

echo
echo "Pruning backups older than 7 days..."
find "$BACKUP_DIR" -type f -name "*.tar.gz" -mtime +7 -delete || true

echo
echo "Backup completed:"
ls -lh "$BACKUP_DIR" | tail -n 20
