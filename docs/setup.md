# VM Setup Instructions

## 1. Install dependencies

sudo apt update
sudo apt install python3 python3-venv podman git

## 2. Setup AI stack folder

mkdir -p ~/ai-stack
cd ~/ai-stack

## 3. Setup Python env

python3 -m venv python-envs/qdrant-env
source python-envs/qdrant-env/bin/activate

pip install qdrant-client fastapi uvicorn sentence-transformers watchdog
``
