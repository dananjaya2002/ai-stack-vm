# Contributing

Thanks for checking out AI Stack VM. This repository is organized as a
portfolio-friendly local AI/RAG stack, so changes should keep setup, security,
and demo flows easy to review.

## Local Checks

Recommended checks before opening a pull request:

```bash
bash -n ai-stack
python -m compileall scripts
cd scripts/dashboard/frontend
npm install
npm run typecheck
npm run build
```

## Repository Hygiene

- Do not commit `.env` files, API keys, model files, logs, vector database data,
  Open WebUI data, or private memory/repository content.
- Keep reusable demo data under `demo/`.
- Keep runtime data under `$AI_STACK_HOME`, not inside the repo.
- Prefer small focused changes that preserve the `./ai-stack` helper workflow.
