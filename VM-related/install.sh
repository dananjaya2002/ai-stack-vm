#!/usr/bin/env bash

echo "Setting up AI stack..."

sudo apt update
sudo apt install -y python3 python3-venv git

mkdir -p ~/ai-stack
cd ~/ai-stack

python3 -m venv python-envs/qdrant-env
source python-envs/qdrant-env/bin/activate

pip install qdrant-client fastapi uvicorn sentence-transformers watchdog tqdm

echo "✅ Setup complete"
