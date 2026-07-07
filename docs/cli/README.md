# CLI Guide

The `./ai-stack` helper is the main operator interface for the project.

## Command Groups

- [Command reference](ai-stack.md)
- [Maintenance flows](maintenance.md)

## Common Flows

First run:

```bash
./ai-stack install
```

Manual run:

```bash
./ai-stack init
./ai-stack build
./ai-stack up
./ai-stack dashboard
./ai-stack status
```

Agentic RAG:

```bash
./ai-stack agentic-rag up
./ai-stack agentic-rag status
./ai-stack agentic-rag logs
./ai-stack agentic-rag down
```

Validation and demo:

```bash
./ai-stack smoke
./ai-stack demo run
./ai-stack benchmark
```

Vector maintenance:

```bash
./ai-stack qdrant collections
./ai-stack qdrant reset demo
```

## Related Docs

- [Setup](../setup/README.md)
- [Operations](../operations/README.md)
- [Root README CLI reference](../../README.md#cli-reference)
