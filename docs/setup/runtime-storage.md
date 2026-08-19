# Runtime Storage

Runtime data is kept outside the source tree. Running `./ai-stack init` creates
the host-managed directories below, using `AI_STACK_HOME` from the root `.env`:

```text
$AI_STACK_HOME/
|-- models/                         GGUF model files
`-- memory/
    |-- engineering-memory/         private notes and documents
    `-- code-memory/                cloned or synchronized repositories
```

Do not commit model files, private notes, indexed repositories, virtual
environments, logs, or generated service data.

## Compose-managed data

Qdrant and Open WebUI do not use root repository folders. Compose stores their
state in the named volumes `qdrant_data` and `open_webui_data`. Use the backup
and restore procedures rather than copying placeholder directories from the
repository.

## Local Python environments

`python-envs/` is an optional ignored location for host-development virtual
environments. It does not need to exist in a clean checkout. For example:

```bash
python3 -m venv python-envs/dashboard
python-envs/dashboard/bin/pip install -r scripts/dashboard/requirements.txt
```

See [Open WebUI runtime settings](open-webui.md) for persisted UI defaults and
recommended local-model configuration.
