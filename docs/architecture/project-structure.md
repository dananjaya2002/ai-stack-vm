# RAG Project Structure

The Python RAG backend uses a `src` package while operational files remain at
the repository root.

```text
src/ai_stack_rag/
|-- ingestion/    filesystem loaders and indexing workflows
|-- chunking/     plain-text and symbol-aware code splitting
|-- embeddings/   lazy embedding-model providers
|-- vectordb/     Qdrant adapters
|-- retrieval/    memory, code, and agentic retrieval boundaries
|-- prompts/      named prompt templates and utility prompt handling
|-- llm/          OpenAI-compatible clients and streaming helpers
|-- api/          memory, code, and agentic FastAPI applications
`-- utils/        configuration, security, logging, and source locations
```

The service containers, `./ai-stack` commands, dashboard jobs, and watchers use
package-native module entry points. `scripts/lib/` contains the shared compute,
hardware, environment, and Compose helpers; `requirements/` contains neutral
Python dependencies, while `config/pytorch-backends.conf` owns Torch selection.

## Configuration

Non-secret defaults live in root `config.yaml`. Values are resolved in this
order, from highest to lowest priority:

1. Existing environment variables such as `QDRANT_HOST` and `LLM_MODEL`.
2. A YAML file passed to `load_settings`, or selected with
   `AI_STACK_CONFIG_FILE`.
3. Root `config.yaml`.
4. Typed safe defaults in `ai_stack_rag.utils.config`.

API keys and passwords remain environment-only. The JSON files in
`config/` remain supported for structured watcher, symbol, and agentic
term rules.

## Entry Points

- `main.py` exposes the agentic application as the default development app.
- The memory, code, and agentic modules under `api/` export `app` for Uvicorn.
- The existing `./ai-stack index` and `./ai-stack search` commands are unchanged.

For local package imports without installing the project, set `PYTHONPATH=src`.
Container images set this automatically.
