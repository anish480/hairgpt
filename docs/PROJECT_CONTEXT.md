# HairGPT — Project Context

## What It Is

HairGPT (branded **MoxieBuddy** in-product) is an AI hair-care chatbot for [Moxie Beauty](https://moxiebeauty.in). It lives as a floating widget on the Shopify storefront and helps customers identify their hair type via photo analysis, get personalized product routines, learn how to use products via tutorial videos, and add products to cart — all from the chat interface.

A secondary **kiosk mode** exists for brand events (full-screen iPad quiz flow with sampler tracking).

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI (Python 3.12), uvicorn |
| AI / LLM | Google Gemini 2.5 Flash via `google-genai` SDK |
| Embeddings | Vertex AI `text-embedding-005` (768-dim) |
| Database | Cloud SQL PostgreSQL 16 + pgvector |
| Hosting | Google Cloud Run (`asia-south1`) |
| Container build | Google Cloud Build → Artifact Registry |
| Secrets | GCP Secret Manager |
| Widget | Vanilla JS IIFE (no framework) |
| Storefront | Shopify (Liquid theme injection) |

## Directory Structure

```
hairgpt/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI routes
│   │   ├── orchestrator.py      # Chat loop: guardrails → retrieval → LLM → tools
│   │   ├── llm.py               # Gemini client, embeddings, photo classifier
│   │   ├── retrieval.py         # Hybrid search (pgvector + FTS)
│   │   ├── recommendations.py   # Deterministic routine builder
│   │   ├── prompts.py           # System prompt / persona
│   │   ├── guardrails.py        # Input + output classifiers
│   │   ├── throttle.py          # Rate + token budget limiting
│   │   ├── session_logger.py    # Chat session persistence
│   │   ├── kiosk.py             # Brand event kiosk mode
│   │   ├── config.py            # Env-based settings (pydantic-settings)
│   │   └── db.py                # asyncpg + Cloud SQL Connector
│   ├── static/                  # Served at /static/ (widget JS, logo, kiosk bg)
│   └── requirements.txt
├── shopify-widget/
│   ├── moxiebuddy-widget.js     # Widget source (synced to backend/static/ at build)
│   ├── theme-snippet-production.liquid
│   └── preview.html
├── data/
│   ├── product_catalog.json     # Product catalog (GCS image URLs)
│   ├── cx_handbook_chunks.json  # Knowledge base chunks
│   └── video_chunks.json        # Tutorial video metadata
├── infra/schemas/postgres.sql   # DDL for all tables
├── docs/                        # Reports, flow diagrams
├── design/                      # Design assets
├── deploy.sh                    # Full Cloud Run deploy (6 steps)
└── Dockerfile                   # python:3.12-slim
```

## API Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Health check |
| POST | `/chat` | Main chat (message, session_id, history) → response + suggested options + routine |
| POST | `/photo/analyze` | Hair photo classification (multipart upload) |
| POST | `/event` | Track widget events (ATC, etc.) — writes to `hairgpt_events` |
| GET | `/static/{filename}` | Static assets (widget JS, images) |
| GET | `/preview` | Widget preview page |
| GET | `/kiosk` | Kiosk mode (brand events) |
| POST | `/kiosk/submit` | Submit kiosk session |
| GET | `/kioskadmin` | Kiosk admin dashboard |

## Key Architecture Decisions

- **Hybrid RAG**: Vector similarity (70%) + full-text search (30%) against `kb_chunks` table.
- **Deterministic recommendations**: LLM picks tool parameters (hair type, concern), but the actual routine is assembled by rules in `recommendations.py` — no hallucinated product combos.
- **Dual guardrails**: Input and output both pass through Gemini Flash classifiers (`thinking_budget=0`) to block off-topic content.
- **Tool calling loop**: Orchestrator supports up to 3 rounds of LLM tool calls (`recommend_routine`, `get_product`).
- **Session throttling**: 10 req/min rate limit + 15k output token budget per session.
- **Product catalog from JSON**: Loaded at startup from `data/product_catalog.json`, not fetched live from Shopify. Images hosted on GCS to avoid Shopify CDN URL rotation.

## Widget Architecture

The widget (`moxiebuddy-widget.js`) is a single self-contained JS file — no build step, no framework.

- **Embedding**: `<script>` tag in Shopify theme via Liquid snippet. Configured through `window.MoxieBuddyConfig`.
- **Session persistence**: `localStorage` key `moxiebuddy_session` (session ID, history, messages, hair context, last routine).
- **Exit-intent**: Auto-opens panel on mouse exit (desktop) or 15s idle (mobile). Once per session via `sessionStorage`.
- **Photo upload**: Sends to `/photo/analyze`, injects classification into chat history.
- **Product carousel**: Renders from `routine` data returned by backend. Includes Add to Cart.
- **Cross-browser video**: Mascot animations use dual-source `<video>` — HEVC MP4 (Safari alpha) first, WebM VP9 (Chrome/Firefox) second. Encoded with `premultiply=inplace=1`.
- **Two copies must stay in sync**: `backend/static/moxiebuddy-widget.js` and `shopify-widget/moxiebuddy-widget.js`. The Dockerfile copies from `shopify-widget/` into the container.

## Infrastructure

| Resource | Value |
|---|---|
| GCP project | `hairgpt-496305` |
| Region | `asia-south1` (Mumbai) |
| Cloud Run service | `hairgpt-preview` |
| Cloud SQL instance | `hairgpt-db` (Postgres 16, `asia-south1-c`) |
| Database | `hairgpt`, users: `postgres` (DDL), `hairgpt-app` (runtime) |
| GCS bucket | `gs://hairgpt-496305-widget-assets/widget/` (mascot videos, product images) |
| Artifact Registry | `hairgpt-repo` in `asia-south1` |
| Runtime SA | `hairgpt-runtime@hairgpt-496305.iam.gserviceaccount.com` |

## Deployment

```bash
bash deploy.sh
```

Runs 6 steps: enable APIs → create Artifact Registry repo → Cloud Build → get compute SA → grant IAM roles → deploy to Cloud Run.

Cloud Run config: 512Mi memory, 1 CPU, 0–3 instances, 120s timeout, unauthenticated access.

**Auth note**: `gcloud auth login` + `gcloud auth application-default login` expire daily. Always verify before deploying.

## Secrets (GCP Secret Manager)

| Secret ID | Purpose |
|---|---|
| `shopify-client-id` | Shopify app client ID |
| `shopify-client-secret` | Shopify app client secret |
| `shopify-storefront-token-dev` | Storefront API token |
| `db-app-password` | Runtime DB password |
| `db-postgres-password` | Postgres superuser password |

Env vars hold secret **names**, not values. `secret_manager.py` fetches at runtime via ADC.

## Shopify App Integration

The `hairgpt` Shopify app connects the backend to the production store (`moxiebeauty-haircare`) via client credentials OAuth.

| Detail | Value |
|---|---|
| App name | `hairgpt` |
| Production store | `moxiebeauty-haircare.myshopify.com` |
| Auth method | Client credentials OAuth (`mint_admin_token()` in `backend/app/clients/shopify.py`) |
| Scopes | `read_orders`, `read_all_orders`, `read_customers`, `unauthenticated_read_product_listings`, etc. |
| Config file | `hairgpt/shopify.app.toml` |

**Important**: Scopes in `shopify.app.toml` only take effect when deployed via Shopify CLI (`shopify app deploy`). If the app was created via Partners dashboard, scopes must be pushed with `shopify app deploy --allow-updates` and the app must be reinstalled on the store for the consent screen to pick them up.

## Conversion Funnel Tracking

End-to-end funnel: **Sessions → Routine recommended → Add to Cart → Purchase**

### How it works

1. **Sessions + Routines** (stages 1–2): Already tracked in `chat_sessions` table. A session with `routine_recommended IS NOT NULL` counts as a routine.

2. **Add to Cart** (stage 3): When a user clicks ATC in the widget carousel:
   - Widget adds `_hairgpt_session` as a Shopify line item property (underscore prefix hides it from customer-facing UI)
   - Widget fires a POST to `/event` with `event: "add_to_cart"` and the product handle
   - Stored in `hairgpt_events` table

3. **Purchase** (stage 4): Reconciled via `backend/scripts/reconcile_conversions.py`:
   - Queries Shopify Admin API (GraphQL) for recent orders
   - Scans line items for `_hairgpt_session` custom attribute
   - Computes attributed revenue (only HairGPT line items) vs total order value
   - Upserts into `hairgpt_conversions` table

### Database tables

| Table | Purpose |
|---|---|
| `chat_sessions` | Session log with routine + prompt version |
| `hairgpt_events` | Real-time widget events (ATC, extensible) |
| `hairgpt_conversions` | Reconciled purchase attributions from Shopify |
| `prompt_versions` | Frozen snapshots of prompt/guardrail config |

### Scripts

| Script | Purpose |
|---|---|
| `backend/scripts/reconcile_conversions.py` | Match Shopify orders to HairGPT sessions. Run daily: `python reconcile_conversions.py --days 1` |
| `backend/scripts/daily_funnel_report.py` | Generate HTML funnel report: `python daily_funnel_report.py -o docs/funnel-report.html` |

### Tracking baseline

Funnel metrics only include sessions from **2026-09-01 13:00 IST** onward. Earlier sessions had no ATC/purchase tracking and are excluded to avoid skewing conversion rates. The baseline is stored as `TRACKING_BASELINE` in `daily_funnel_report.py`.

## Prompt Versioning

Every versionable component (system prompt, guardrails, generation params, recommendation rules) has a semver in `backend/app/prompt_versions.py`. At startup, the bundle is SHA-256 hashed to a 12-char fingerprint and registered in the `prompt_versions` table. Every chat session is tagged with the active fingerprint via `chat_sessions.prompt_version`.

This enables before/after comparison in the funnel report's "By Prompt Version" breakdown. Baseline fingerprint: `0564fdeccf64` (all components at v1.0.0).

## Recent History

```
(uncommitted) Conversion funnel tracking, Shopify app scopes deploy, prompt versioning
281bb01 Fix Safari showing native video controls on mascot videos
56851d5 Landing page UI refresh: new tagline, layout reorder, shadow fix
37ffabc Widget UX: new chat reset, session restore, exit-intent, bubble spacing
ef94db6 Mirror product images to GCS, gitignore .mov sources
fbe4e94 Fix mascot halo with premultiplied HEVC, restore animated bubble icon
b1d7b32 Fix Safari alpha: HEVC MP4 first in source order, static PNG for bubble
d38f4cc Add exit-intent trigger to widget and July performance report
ec71f5c Fix recommendation engine, widget perf, tutorials, and session handling
9cbc07e Remove rollout gating — ship widget to 100% of users
2bdbfd4 Phase 4: Production deployment, kiosk mode, Shopify widget, guardrails
```

## Key Learnings

- **Shopify line item properties**: Prefixing a property key with `_` hides it from the customer-facing storefront (cart page, checkout, order confirmation) but keeps it visible in Shopify admin and accessible via Admin API.
- **Shopify app scopes vs install**: Declaring scopes in `shopify.app.toml` doesn't automatically grant them. The config must be deployed via `shopify app deploy`, and the app must be reinstalled on the store for the new scopes to take effect.
- **asyncpg datetime handling**: Shopify API returns ISO timestamps as strings. asyncpg requires native `datetime` objects for `TIMESTAMPTZ` columns — use `dateutil.isoparse()` to convert.
- **Funnel baseline fairness**: When adding new tracking stages to an existing system, only include sessions from the tracking deployment date onward. Including historical sessions with no possibility of downstream conversion creates misleading funnel drop-off rates.
