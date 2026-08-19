# Architecture

AI Stack VM is a local-first AI/RAG stack built around containerized services,
OpenAI-compatible APIs, and predictable runtime folders under `$AI_STACK_HOME`.

## Main Services

| Service | Role |
|---|---|
| `vm-llama` | llama.cpp OpenAI-compatible model server. |
| `qdrant` | Vector database for engineering memory and code chunks. |
| `memory-proxy` | RAG proxy over markdown engineering notes. |
| `code-proxy` | RAG proxy over indexed code repositories. |
| `agentic-rag` | Optional multi-step retrieval connector for Open WebUI. |
| `open-webui` | Browser chat UI. |
| `dashboard` | FastAPI + React management UI for status, logs, files, indexing, and watchers. |

## Topology

```text
Open WebUI / browser
  -> vm-llama       http://vm-llama:8082/v1
  -> memory-proxy   http://memory-proxy:9002/v1
  -> code-proxy     http://code-proxy:9001/v1
  -> agentic-rag    http://agentic-rag:9200/v1

dashboard
  -> vm-llama       http://vm-llama:8082/v1
  -> qdrant         http://qdrant:6333
  -> mounted memory/code folders

memory-proxy/code-proxy/agentic-rag
  -> qdrant
  -> vm-llama
```

## Runtime Data

The default runtime path is `$AI_STACK_HOME`, normally `$HOME/ai-stack`:

```text
$AI_STACK_HOME/
|-- models/
`-- memory/
    |-- engineering-memory/
    `-- code-memory/
```

Qdrant and Open WebUI use named container volumes. Model files and private
memory/code content should not be committed to Git.

## More

- [Services](services.md)
- [Data flow](data-flow.md)
- [RAG project structure](project-structure.md)
- [Ports](../ports.md)
- [Root README](../../README.md)
