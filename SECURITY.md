# Security Policy

AI Stack VM is designed as a local-first AI/RAG stack. Treat indexed notes,
repositories, logs, dashboard uploads, and model endpoints as private data.

## Supported Use

- Keep default local bindings for model, proxy, and vector database services.
- Use `SECURITY_MODE=production` with a strong `AI_STACK_API_KEY` before exposing
  OpenAI-compatible endpoints beyond a trusted local machine.
- Use dashboard authentication in production by setting:
  - `DASHBOARD_AUTH_MODE=auto`
  - `DASHBOARD_ADMIN_PASSWORD_HASH`
  - `DASHBOARD_SESSION_SECRET`
- Put HTTPS in front of any browser-facing deployment that crosses a network
  boundary.

## Reporting Issues

If you find a security issue in this portfolio project, please open a private
GitHub security advisory if available, or contact the repository owner directly.
Do not include secrets, private indexed content, or exploit details in a public
issue.

## Sensitive Files

Do not commit:

- `.env` or generated service env files
- model files
- Qdrant/Open WebUI runtime data
- Python virtual environments
- logs
- private engineering notes or private repositories
