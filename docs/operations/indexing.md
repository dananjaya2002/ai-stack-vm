# Indexing

Indexing turns local files into vector-searchable chunks in Qdrant.

## Engineering Memory

Document memory discovers Markdown, plain text, Python, JSON, YAML, and PDF
files. PDF text is extracted page by page with `pypdf`. Image-only or scanned
PDFs need OCR before indexing because they do not contain extractable text.

PDFs are not converted to Markdown and no sidecar file is created. Extracted
text is held in memory, split into consecutive non-overlapping chunks using the
configured document chunk size (500 characters by default), embedded, and
stored in Qdrant with the original PDF path and filename as metadata. The PDF
on disk is not modified.

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

## Dashboard Indexing

The dashboard can start full or targeted indexing jobs from the Indexing tab.
The `indexer` service is a one-shot helper and should not stay running.

## Related Docs

- [Data flow](../architecture/data-flow.md)
- [Demo mode](../examples/demo-mode.md)
- [Troubleshooting](troubleshooting.md)
