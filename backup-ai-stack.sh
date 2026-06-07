#!/usr/bin/env bash
set -e

BACKUP_DIR="$HOME/ai-stack/backups"
DATE=$(date +"%Y-%m-%d_%H-%M-%S")

mkdir -p "$BACKUP_DIR"

echo "Backing up Open WebUI data..."
tar -czf "$BACKUP_DIR/open-webui-$DATE.tar.gz" -C "$HOME/ai-stack" open-webui || true

echo "Backing up Qdrant data if exists..."
if [ -d "$HOME/ai-stack/qdrant" ]; then
  tar -czf "$BACKUP_DIR/qdrant-$DATE.tar.gz" -C "$HOME/ai-stack" qdrant
fi

echo "Backing up systemd user units..."
tar -czf "$BACKUP_DIR/systemd-user-$DATE.tar.gz" -C "$HOME/.config" systemd containers 2>/dev/null || true

echo "Backup completed:"
ls -lh "$BACKUP_DIR" | tail
