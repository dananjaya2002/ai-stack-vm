# AI Stack VM Documentation

This folder is the operator and reviewer documentation for AI Stack VM. The
root [README](../README.md) is the portfolio landing page; these docs go deeper
into architecture, setup, APIs, operations, and production hardening.

## Start Here

| Goal | Read |
|---|---|
| Understand the system design | [Architecture](architecture/README.md) |
| Install or configure the stack | [Installation](setup/installation.md) |
| Select CPU or NVIDIA compute | [Hardware and GPU](setup/hardware-detection.md) |
| Run production login/API-key mode | [Production setup](setup/production.md) |
| Call the OpenAI-compatible APIs | [API reference](api/README.md) |
| Try demo data and sample requests | [Examples](examples/README.md) |
| Use the `./ai-stack` helper | [CLI guide](cli/README.md) |
| Operate, debug, and recover services | [Operations](operations/README.md) |
| Review exposure and auth guidance | [Security](security/README.md) |

## Documentation Map

- [Architecture](architecture/README.md): service responsibilities, networking,
  runtime data, and RAG data flow.
- [Setup](setup/README.md): first run, local development, production mode, and
  single-root `.env` configuration.
- [API](api/README.md): OpenAI-compatible endpoints, dashboard API, and
  Agentic RAG debug endpoints.
- [Examples](examples/README.md): demo mode, curl examples, Open WebUI
  connections, and useful test questions.
- [CLI](cli/README.md): `./ai-stack` command reference and maintenance flows.
- [Operations](operations/README.md): status checks, logs, indexing, backups,
  and troubleshooting.
- [Security](security/README.md): dashboard login, bearer auth, network
  bindings, and HTTPS guidance.
- [Benchmarks](benchmarks/README.md): benchmark command output and how to
  capture reviewer-ready measurements.
- [Ports](ports.md): service port reference.
- [Media](media/README.md): architecture diagram and placeholder screenshots.

## Core Project Files

- [`.env.example`](../.env.example): single runtime configuration template.
- [`docker-compose.yml`](../docker-compose.yml): main stack services.
- [`docker-compose.dashboard.yml`](../docker-compose.dashboard.yml): dashboard
  and one-shot indexer helper.
- [`docker-compose.agentic-rag.yml`](../docker-compose.agentic-rag.yml):
  optional Agentic RAG connector.
- [`ai-stack`](../ai-stack): primary helper CLI.

## Notes

The project now uses one root `.env` as the runtime configuration source. Do not
commit real `.env` files, model files, logs, Qdrant data, Open WebUI data, or
private memory/code repositories.
