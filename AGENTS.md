# AGENTS.md

## Cursor Cloud specific instructions

This repo is a single product: the **Pearson BTEC IT Auto-Grader** — a FastAPI web app
(Arabic RTL, Jinja2 server-rendered UI) that grades BTEC IT coursework with an LLM
(Gemini by default). See `SETUP.md` (Arabic) and `infra/docs/architecture.md` for details.

### Services

- **Main app (required):** FastAPI + Uvicorn defined in `main.py`. Single process serves the
  UI, API, and in-process batch grading workers. Uses SQLite (`ai_grader.db`, auto-created on
  startup) — no separate DB server needed for local dev.
- **WhatsApp sidecar (optional):** Node service in `whatsapp_service/`. Keep it OFF in dev
  (`WHATSAPP_AUTO_START=false`). Not needed for grading or any core flow.
- **Celery/Redis, MinIO/S3, Postgres, Docker sandbox (optional):** only used by the
  production Docker stack (`docker compose up`) and async runtime/CV pipelines. Not required
  for local dev, tests, or the core grading UI.

### Running the app (dev)

- The update script provisions the `.venv` and installs dependencies. Activate it first:
  `source .venv/bin/activate`.
- A `.env` is required. It is git-ignored, so it lives only in the VM (not in the repo). If it
  is ever missing, recreate it: `cp .env.example .env` then set a `SECRET_KEY`
  (`python -c "import secrets; print(secrets.token_urlsafe(48))"`) and set
  `WHATSAPP_AUTO_START=false`.
- Start the dev server: `python run_dev_server.py` (disables the WhatsApp sidecar and uses a
  single batch worker). `.env`'s `PORT=5556` wins over the launcher's default, so the server
  listens on **http://localhost:5556**. `python main.py` also works.
- Health check: `curl http://localhost:5556/health` (expect `"status":"ok"` with
  `checks.database.ok = true`). Unauthenticated `/` returns a 302 redirect to `/login`.
- New-user flow works out of the box: `/register` (email/password; password needs upper +
  lower + digit) auto-logs in and redirects to `/dashboard`.

### AI grading key (non-obvious)

The app **boots and the auth/dashboard/upload UI works without any AI key**, but actual
grading calls need a provider. Set `GEMINI_API_KEY` in `.env` (`AI_PROVIDER=gemini`) to enable
end-to-end grading. Without it, `/health` is still `ok` (it only checks the DB), but grading
requests will fail. `DISABLE_OLLAMA_FALLBACK=true` avoids confusing "connection refused"
errors to a non-existent local Ollama.

### Lint / test / build

- **Lint:** `flake8 app main.py` (config in `.flake8`). The repo currently reports many
  pre-existing style findings (mostly whitespace); these are not caused by env setup.
- **Types:** `pyright` config in `pyrightconfig.json` (points at `.venv`).
- **Tests:** `python -m pytest tests/ -q`. As of setup, ~396 pass and ~14 fail. The failures
  are pre-existing code/test drift (e.g. `test_rule_bundle` expects `BASIC` but code returns
  `STANDARD`), NOT environment problems — do not treat them as setup breakage. The CI preflight
  subset in `.github/workflows/staging-deploy.yml` passes cleanly.
- Running the test suite writes throwaway artifacts under `uploads/runtime_sessions/`,
  `uploads/runtime/batch_progress/`, and `uploads/replay_snapshots/`. Don't commit those.
- There is no separate build step for the app (server-rendered templates).
