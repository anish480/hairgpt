# HairGPT

Moxie Beauty's hair-care chatbot for the Shopify storefront. GCP-native stack: Vertex AI (Gemini 2.5) for LLMs, Cloud Run for compute, Cloud SQL Postgres 16 + pgvector for KB + sessions, Shopify Theme App Extension for widget delivery.

## Status

**Live build state, learnings, and resumption points are at the top of [`HairGPT_Implementation_Plan.md`](./HairGPT_Implementation_Plan.md) — read the "Build status (live)" section first.** That section is the source of truth between sessions; the rest of the plan is the unchanging long-form spec.

## Layout

```
.
├── HairGPT_Implementation_Plan.md    # The plan + live "Build status (live)" section
├── README.md                          # You are here
├── .gitignore
│
├── backend/                           # FastAPI service (Python 3.14, uv)
│   ├── app/
│   │   ├── main.py                   # FastAPI entrypoint
│   │   ├── config.py                 # pydantic-settings
│   │   ├── llm.py                    # google-genai (Vertex) wrapper for Gemini 2.5
│   │   ├── db.py                     # asyncpg + cloud-sql-python-connector pool
│   │   └── clients/
│   │       ├── secret_manager.py     # Secret Manager accessor
│   │       └── shopify.py            # Admin client_credentials minter + GraphQL helper
│   ├── scripts/
│   │   ├── smoke.py                  # End-to-end: Shopify + Vertex + Cloud SQL
│   │   ├── init_db.py                # Apply schema + grants
│   │   └── mint_storefront_token.py  # Mint a Storefront token per store via Admin API
│   ├── pyproject.toml                # uv-managed deps
│   └── .env.example                  # Copy to .env to override defaults
│
├── hairgpt/                           # Shopify CLI app scaffold (Theme App Extension lives here in Phase 2)
│   └── shopify.app.toml              # client_id + scopes; client_secret lives in Secret Manager
│
├── infra/
│   └── schemas/postgres.sql          # Cloud SQL DDL (extensions, tables, indexes)
│
└── scripts/
    └── mint_admin_token.sh           # Bash helper for ad-hoc Shopify Admin tokens
```

## Prerequisites for a new machine

- **gcloud CLI** authenticated with an account that has the right IAM on GCP project `hairgpt-496305` (Vertex AI user, Cloud SQL client, Secret Manager accessor, etc.)
- **Application Default Credentials** for Vertex + Cloud SQL Python Connector:
  ```bash
  gcloud auth application-default login
  ```
- **uv** (Python package manager):
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
- (optional) **cloud-sql-proxy** for ad-hoc psql:
  ```bash
  curl -fsSL -o ~/.local/bin/cloud-sql-proxy \
    https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.14.3/cloud-sql-proxy.linux.amd64
  chmod +x ~/.local/bin/cloud-sql-proxy
  ```
- (Phase 2+) **Shopify CLI** for the `hairgpt/` Theme App Extension:
  ```bash
  npm install -g @shopify/cli @shopify/theme
  ```

## Bootstrap

### With uv (canonical, fastest)
```bash
cd backend/
cp .env.example .env
uv sync
uv run python -m scripts.smoke   # Validates Shopify Admin + Vertex Gemini + Cloud SQL pipes
```

### With pip (if uv isn't installed)
```bash
cd backend/
cp .env.example .env
python3.12 -m venv .venv && source .venv/bin/activate    # 3.12+ required (we use 3.14 locally)
pip install -r requirements.txt
python -m scripts.smoke
```

`requirements.txt` mirrors `uv.lock` — versions are identical between the two paths. Regenerate after a `uv sync`:
```bash
uv export --format requirements-txt --no-hashes --no-emit-project --output-file requirements.txt
```

Expected smoke output: token mint, GraphQL `shop.name`, Gemini response, Postgres version + extensions + table list, ending in `[smoke] all pipes OK`. If any pipe fails, see the Learnings & gotchas section in the plan — most failure modes are covered.

Once smoke passes, follow the **Resumption guide** at the top of the plan to pick the next task.

## Secrets

Nothing sensitive is in this repo. All credentials live in **GCP Secret Manager** on project `hairgpt-496305`:

| Secret | Purpose |
|---|---|
| `shopify-client-id` / `shopify-client-secret` | Dev Dashboard OAuth app creds |
| `shopify-storefront-token-dev` | Long-lived Storefront API token for dev store |
| `db-app-password` | `hairgpt-app` runtime DB user |
| `db-postgres-password` | Postgres superuser (DDL only) |

Backend code accesses these via `app.clients.secret_manager.get_secret(secret_id)` (lru_cached).
