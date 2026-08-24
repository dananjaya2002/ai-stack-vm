# Indexing

Indexing turns local files into vector-searchable chunks in Qdrant.

## Engineering Memory

Document memory discovers Markdown (`.md`) files only. Markdown text is split
into consecutive non-overlapping chunks using the configured document chunk
size (500 characters by default), embedded, and stored in Qdrant with the
original path and filename as metadata.

Put markdown notes under:

```text
$AI_STACK_HOME/memory/engineering-memory
```

Index all engineering memory:

```bash
./ai-stack index memory
```

Index a specific file or folder:

```bash
./ai-stack index memory "$AI_STACK_HOME/memory/engineering-memory/path/to/file.md"
```

## Code Repositories

Put repositories under:

```text
$AI_STACK_HOME/memory/code-memory/<repo-name>
```

Index a repo:

```bash
./ai-stack index code "$AI_STACK_HOME/memory/code-memory/<repo-name>"
```

The code watcher debounces repository events and sends every file that becomes
ready in the same window to one incremental indexing process. The embedding
model and Qdrant client are initialized once for that batch, and each file's
chunks are embedded together. Changes detected while a batch is running stay
queued for the next batch.

## Dashboard Indexing

The dashboard can start full or targeted indexing jobs from the Indexing tab.
The `indexer` service is a one-shot helper and should not stay running.

## Related Docs

- [Data flow](../architecture/data-flow.md)
- [Demo mode](../examples/demo-mode.md)
- [Troubleshooting](troubleshooting.md)
