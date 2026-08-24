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
bash scripts/install-python-dependencies.sh --backend cpu requirements/dashboard.txt
```

## Installer thresholds

- Runtime filesystem: remaining model bytes plus 10 GiB minimum or 20 GiB recommended.
- Container filesystem: 10/15 GiB minimum/recommended for CPU images.
- Container filesystem: 20/30 GiB minimum/recommended for GPU images.

If both paths are on the same filesystem, the requirements are summed. Below a
minimum, installation stops before download. Between minimum and recommended,
installation continues with a warning.

See [Open WebUI runtime settings](open-webui.md) for persisted UI defaults and
recommended local-model configuration.
