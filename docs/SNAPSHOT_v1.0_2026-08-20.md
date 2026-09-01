# HairGPT Project Snapshot — v1.0 (2026-08-20)

Versioned point-in-time image of the HairGPT project. Baseline for all future prompt, guardrail, and conversation flow changes.

---

## 1. Project Timeline

| Date | Commit | Milestone |
|---|---|---|
| 2026-05-16 | `8c2b06c` | Genesis — BQ infra, Shopify dev env, model configs, orchestration layer |
| 2026-05-19 | `98d3e8b` | Phase 2+3 — RAG chatbot, photo classifier, product ingestion, Streamlit UI |
| 2026-06-18 | — | First live user session recorded in Cloud SQL |
| 2026-06-30 | `2bdbfd4` | Phase 4 — Cloud Run deployment, Shopify widget, guardrails, kiosk mode, session logging |
| 2026-07-01 | `9cbc07e` | 100% rollout — removed rollout gating |
| 2026-07-01 | `5583acd` | Prompt fixes — cold-opener, try-different, typo tolerance, output guardrail loosening |
| 2026-07-02 | `ad81b31` | Widget UX — bubble animation, scroll, zoom, competitor handling |
| 2026-07-02 | `1c003bf` | Auto-focus fix — blur on panel open for iOS keyboard |
| 2026-07-06 | `ec71f5c` | Recommendation engine fix, perf (gzip, caching), tutorials, GA4 session binding |
| 2026-07-30 | `d38f4cc` | Exit-intent trigger, July performance report |
| 2026-08-05 | `b72712a`→`fbe4e94` | Animated mascot video — 4 iterations (Safari alpha, HEVC encoding, source order) |
| 2026-08-10 | `ef94db6` | Product images mirrored to GCS (Shopify CDN URL rotation fix) |
| 2026-08-10 | `37ffabc` | Widget UX batch — new chat reset, session restore, exit-intent simplification |
| 2026-08-10 | `56851d5` | Landing page UI refresh — new tagline, layout reorder, suggestion cards |
| 2026-08-11 | deployed | Safari video controls fix (committed retroactively 2026-08-14 as `281bb01`) |

**Total commits:** 17 | **Active development period:** 97 days (May 16 → Aug 20, 2026)

---

## 2. Session Statistics (D0 → 2026-08-20)

### Overall

| Metric | Value |
|---|---|
| Total sessions | 19,606 |
| Photo uploads | 6,844 (34.9%) |
| Routine recommendations | 10,684 (54.5%) |
| Average messages per session | 3.6 |
| Max messages in a session | 167 |
| First session | 2026-06-18 |
| Latest session | 2026-08-20 |
| Kiosk sessions (brand events) | 230 |

### Weekly Session Volume

| Week of | Sessions |
|---|---|
| 2026-06-15 | 59 |
| 2026-06-22 | 1 |
| 2026-06-29 | 792 |
| 2026-07-06 | 1,561 |
| 2026-07-13 | 1,401 |
| 2026-07-20 | 1,152 |
| 2026-07-27 | 1,516 |
| 2026-08-03 | 1,919 |
| 2026-08-10 | 7,696 |
| 2026-08-17 | 3,509 |

### Platform Breakdown

| Platform | Sessions | Share |
|---|---|---|
| Linux (Android) | 10,437 | 53.2% |
| iOS | 7,368 | 37.6% |
| Windows | 1,149 | 5.9% |
| macOS | 596 | 3.0% |
| Unknown | 56 | 0.3% |

---

## 3. Architecture

### System Components

```
Shopify storefront (moxiebeauty.in)
  └── <script> injects moxiebuddy-widget.js (from Cloud Run /static/)
        ├── Panel UI (chat, photo upload, product carousel, ATC)
        ├── GA4 cookie sniffing (stored, not used)
        └── POST /chat, POST /photo/analyze
              │
Cloud Run (hairgpt-preview, asia-south1)
  ├── FastAPI (uvicorn, port 8080)
  │     ├── Input guardrail (Gemini Flash classifier)
  │     ├── RAG retrieval (pgvector + FTS hybrid search)
  │     ├── Orchestrator (Gemini Flash + tool calling, up to 3 rounds)
  │     │     ├── recommend_routine → deterministic routine builder
  │     │     └── get_product → catalog lookup
  │     ├── Output guardrail (Gemini Flash classifier)
  │     ├── Session logger → chat_sessions table
  │     └── Throttle (10 req/min in-memory, 15k token budget in DB)
  │
Cloud SQL (PostgreSQL 16, hairgpt-db)
  ├── kb_chunks (58 rows, cx_handbook — vector + FTS indexed)
  ├── chat_sessions (19,606 rows — primary runtime table)
  ├── kiosk_sessions (230 rows)
  ├── conversations (0 rows — unused)
  ├── messages (0 rows — unused)
  └── message_feedback (0 rows — unused)
```

### Key Files

| File | Purpose |
|---|---|
| `backend/app/main.py` | FastAPI routes |
| `backend/app/orchestrator.py` | Chat loop: guardrails → RAG → LLM → tools → post-processing |
| `backend/app/prompts.py` | System prompt (SYSTEM_PROMPT + build_system_prompt()) |
| `backend/app/guardrails.py` | Input/output classifiers |
| `backend/app/llm.py` | Gemini client, embeddings, hair photo classifier |
| `backend/app/recommendations.py` | Deterministic routine builder (7 product lines) |
| `backend/app/retrieval.py` | Hybrid pgvector + FTS search |
| `backend/app/session_logger.py` | Upsert to chat_sessions |
| `backend/app/throttle.py` | Rate limiting + token budget |
| `backend/static/moxiebuddy-widget.js` | Widget JS (served from Cloud Run) |
| `shopify-widget/moxiebuddy-widget.js` | Widget JS (Shopify theme copy, synced at build) |
| `data/product_catalog.json` | Product catalog (GCS image URLs) |
| `deploy.sh` | Full Cloud Run deployment (6 steps) |

### Database Schema — `chat_sessions` (runtime table)

| Column | Type | Notes |
|---|---|---|
| `session_id` | text | PK |
| `device_info` | jsonb | User agent, platform, screen size, language, referrer |
| `ga_context` | jsonb | GA4 cookies, client ID, VWO experiments, GTM status |
| `conversation_log` | jsonb | Full message history (images replaced with placeholder) |
| `hair_context` | jsonb | Photo classification results |
| `routine_recommended` | jsonb | Last recommended routine |
| `message_count` | integer | Count of user messages |
| `photo_uploaded` | boolean | OR-ed (once true, always true) |
| `created_at` | timestamptz | First interaction |
| `updated_at` | timestamptz | Last interaction |
| `metadata` | jsonb | Token budget tracking (`total_output_tokens`) |

---

## 4. Prompt & Guardrail State (Baseline — pre-versioning)

### System Prompt (`prompts.py`)

- **Persona**: MoxieBuddy — hair-care educator for Moxie Beauty
- **Response length**: 60 words max, 2-3 sentences
- **Conversation flow**: Gather hair type (photo preferred) + primary concern → call `recommend_routine`
- **Security**: Injection defenses, no persona switching, no prompt leaking
- **Competitor handling**: Educative, acknowledge competitor strengths, position Moxie factually
- **Brand rules**: Specific terminology (no "harsh chemicals", use full product names, no "CGM")
- **5 few-shot examples** demonstrating tone and off-topic redirection
- **OPTIONS line** at end of every response for suggested follow-up buttons

### Input Guardrail (`guardrails.py`)

- Gemini Flash classifier, temperature=0.0, thinking_budget=0
- ALLOW: hair/scalp care, Moxie products, greetings, shipping, competitor comparisons
- BLOCK: code, politics, prompt injection, roleplay, medical, homework
- Misspelling leniency: if plausibly hair-related, ALLOW
- Fails open on exceptions

### Output Guardrail (`guardrails.py`)

- Gemini Flash classifier, temperature=0.0, max_output_tokens=5, thinking_budget=0
- Biased toward PASS (false positives worse than false negatives)
- Fallback: "Hmm, let me try that again. What's going on with your hair..."
- Fails open on exceptions

### Hair Photo Classifier (`llm.py`)

- Gemini Flash multimodal, thinking_budget=2048
- Paul Mitchell 1A-3C system with image quality assessment
- Structured JSON output schema with tiebreak rules
- Retry mechanism for inconclusive images

### Generation Parameters

| Context | Model | Temperature | Max tokens | Thinking budget |
|---|---|---|---|---|
| Chat | gemini-2.5-flash | 0.7 | 1024 | 0 |
| Input guardrail | gemini-2.5-flash | 0.0 | 100 | 0 |
| Output guardrail | gemini-2.5-flash | 0.0 | 5 | 0 |
| Hair classifier | gemini-2.5-flash | (default) | (default) | 2048 |

### Tool Definitions (`orchestrator.py`)

- `recommend_routine(hair_type, formation, texture, primary_concern, ...)` → deterministic routine
- `get_product(product_handle)` → catalog lookup

### Recommendation Logic (`recommendations.py`)

7 product lines, 2-phase composable builder:
- **Phase 1 (Wash)**: ScalpSOS (scalp concern) / HydroRepair (damage/chemical/color) / Gentle Cleanse (default)
- **Phase 2 (Style/Treat)**: Curly Vibe Setter / Wavy Vibe Setter / Frizz Serum / HA Serum (by formation + concern)
- Optional scalp serum add-on

---

## 5. Infrastructure

| Resource | Value |
|---|---|
| GCP project | `hairgpt-496305` |
| Region | `asia-south1` (Mumbai) |
| Cloud Run service | `hairgpt-preview` |
| Current revision | `hairgpt-preview-00042-8gr` |
| Cloud SQL instance | `hairgpt-db` (Postgres 16) |
| GCS bucket | `gs://hairgpt-496305-widget-assets/widget/` |
| Artifact Registry | `hairgpt-repo` |
| Runtime SA | `hairgpt-runtime@hairgpt-496305.iam.gserviceaccount.com` |
| Cloud Run config | 512Mi / 1 CPU / 0-3 instances / 120s timeout |

---

## 6. Known Gaps (as of this snapshot)

1. **No purchase attribution** — ATC sends `{id, quantity}` with no session ID, cart attributes, or line item properties. Cannot trace purchases back to HairGPT.
2. **No widget event tracking** — GA4 cookies are sniffed and stored but no events are fired (no `gtag()` calls for panel open, message, photo, ATC).
3. **No prompt versioning** — Prompts are inline constants with no version identifiers. No way to compare behavior across changes.
4. **`chat_sessions` schema not tracked** — The primary runtime table was created manually and is missing from `infra/schemas/postgres.sql`.
5. **`conversations`, `messages`, `message_feedback` tables unused** — Schema exists but 0 rows; all runtime data goes to `chat_sessions`.
6. **Rate limiting is in-memory only** — Won't survive restarts, not shared across instances.
7. **Product catalog loaded from JSON at startup** — Not synced live from Shopify.
8. **KB chunks only 58 rows (cx_handbook)** — Product and video chunks may have been ingested but pruned or replaced.

---

## 7. Key Learnings & Architectural Decisions

1. **HEVC alpha encoding**: Must use `premultiply=inplace=1` before `hevc_videotoolbox`. Tag with `hvc1`. HEVC MP4 must be first `<source>`, WebM second.
2. **Safari video controls**: Safari renders native controls on `<video>` inside `<button>` even without `controls` attr. Fix: `::-webkit-media-controls` CSS + `disablePictureInPicture`.
3. **CSS specificity in widget**: `#mb-widget *{margin:0}` overrides class-level margins. Always prefix with `#mb-widget`.
4. **No auto-focus on mobile**: iOS keyboards are disruptive. Explicit `blur()` on panel open.
5. **Output guardrail false positives**: Initial implementation was too aggressive — blocked valid hair questions. Loosened bias toward PASS.
6. **Shopify CDN URL rotation**: Product image URLs expire. Mirrored 71 images to GCS.
7. **Deterministic recommendations**: LLM picks parameters, rules assemble the routine. Prevents hallucinated product combos.
8. **gcloud auth**: Expires daily. Always verify before deploying (`gcloud auth login` + `gcloud auth application-default login`).
