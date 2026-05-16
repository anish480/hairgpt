# HairGPT Backend

FastAPI service for the HairGPT chatbot. Lives at the repo root alongside `hairgpt/` (Shopify app) and `scripts/`.

## Local dev

Prereqs: `uv` (`curl -LsSf https://astral.sh/uv/install.sh | sh`), gcloud authed as a principal with Vertex AI + Secret Manager access.

```bash
cd backend/
cp .env.example .env

# Application Default Credentials for Vertex AI + Secret Manager
gcloud auth application-default login

# Install deps + run smoke test
uv sync
uv run python -m scripts.smoke

# Run the API
uv run uvicorn app.main:app --reload
```

## Layout

```
backend/
├── app/
│   ├── main.py              # FastAPI entrypoint
│   ├── config.py            # Settings via env / .env
│   ├── llm.py               # Vertex AI Gemini wrapper
│   └── clients/
│       ├── secret_manager.py
│       └── shopify.py       # Token-minter + Admin GraphQL helper
└── scripts/
    └── smoke.py             # Smoke test: Shopify + Vertex pipes
```

More modules (orchestrator, retrieval, ingest, DB) added as Phase 1 progresses.
