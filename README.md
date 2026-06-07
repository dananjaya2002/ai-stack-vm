# AI Stack (Local RAG System)

This repository contains:

- Qdrant vector memory pipeline
- Incremental indexing system
- Memory API (OpenAI compatible)
- Continue + Open WebUI integration

## Setup

1. Create venv
2. Install dependencies
3. Run memory API
4. Run watcher

## Architecture

User → Memory API → Qdrant → llama.cpp → Response
