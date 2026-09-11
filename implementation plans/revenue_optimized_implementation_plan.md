# HairGPT Sprint 1: Implementation Plan

12 changes across observability, conversation quality, and content. Every spec targets a specific file and function — built to be executed by Claude Code against the current codebase.

| Metric | Value | Note |
|--------|-------|------|
| Changes | 12 | across 9 source files + 1 new |
| Baseline Conversion | ~1.4% | session → Shopify order |
| Current Prompt Version | `60e8545dad3d` | will change after this sprint |
| Corpus Size | 58 | chunks (52 CX + 6 video) |

## Contents

- **A1** RAG Chunk Tracking
- **A2** Langfuse Integration
- **A3** Guardrail Health Monitoring
- **A4** Token Budget Warnings
- **B1** Start Small + Novice Detection
- **B2** adjust_routine Tool
- **B3** Post-Rec Education
- **B4** Tradeoff Education
- **B5** Opening Message Update
- **B6** MoxieBuddy → HairGPT Rename
- **C1** Tutorial Overhaul
- **C2** Video Chunk Expansion

## Constraints

> **No sales tactics.** No discounts, urgency, or pressure language. Users buy because they see value.

> **Clinical backing.** All education must be grounded in the CX handbook or product science. No hallucinated claims.

> **60-word limit stays.** The mobile-first response limit is unchanged. Education fits within it or gets a follow-up turn.

> **Measure before relaxing guardrails.** Output guardrail behavior is logged, not changed. Relaxation is conditional on <5% false-positive rate.

> **Prompt version bumps.** Every prompt or tool schema change bumps the relevant version constant in `prompt_versions.py` so before/after comparison works.

## Dependency Graph

Three workstreams run in parallel. Within each, items are ordered top-to-bottom by dependency.

**Observability:** A1 → A2 → A3 → A4

**Conversation:** B1 → B2 → B3 → B4 → B5 → B6

**Content:** C1 → C2

A2 depends on A1 (chunk metadata feeds traces). A3 integrates with A2 (spans). B6 is a rename that touches files across all workstreams — do it first so no merge conflicts. All 12 changes ship in one deployment; observability tracks each experiment's impact.

---

## A1 — RAG Chunk Tracking `[Observability]`

### Rationale

`format_retrieval_context()` currently strips all chunk metadata (id, score, source_id, product_refs) before injecting into the system prompt. This means there is zero visibility into which chunks influenced a response, making it impossible to debug retrieval quality or identify corpus gaps.

### Files

- `backend/app/retrieval.py`
- `backend/app/orchestrator.py`
- `backend/app/session_logger.py`
- `backend/app/main.py`

### retrieval.py

**Current (line 68–73):**

```python
def format_retrieval_context(chunks: list[RetrievedChunk]) -> str:
    parts = []
    for i, c in enumerate(chunks, 1):
        label = c.chunk_type.replace("_", " ").title()
        parts.append(f"[{label}] {c.content}")
    return "\n\n---\n\n".join(parts)
```

**Target:**

```python
def format_retrieval_context(chunks: list[RetrievedChunk]) -> tuple[str, list[dict]]:
    """Format chunks for system prompt and return metadata for logging."""
    parts = []
    chunk_meta = []
    for i, c in enumerate(chunks, 1):
        label = c.chunk_type.replace("_", " ").title()
        # Include chunk ref in prompt so model can cite sources
        parts.append(f"[{label} | ref:{c.id}] {c.content}")
        chunk_meta.append({
            "chunk_id": c.id,
            "chunk_type": c.chunk_type,
            "source_id": c.source_id,
            "score": round(c.score, 4),
            "product_refs": c.product_refs,
        })
    return "\n\n---\n\n".join(parts), chunk_meta
```

### orchestrator.py

**Current (line 175–176):**

```python
chunks = await retrieve(user_message, top_k=5)
retrieval_context = format_retrieval_context(chunks)
```

**Target:**

```python
chunks = await retrieve(user_message, top_k=5)
retrieval_context, chunk_meta = format_retrieval_context(chunks)
```

Update the `chat()` return signature to include `chunk_meta` (add it as the 7th element of the returned tuple). Update the return statement at line 246 accordingly.

### session_logger.py

Add `retrieval_chunks: list[dict] | None = None` parameter to `log_session()`. Store in the existing `metadata` JSONB column:

```python
# In the INSERT ... ON CONFLICT query, add to the metadata merge:
# Before: metadata JSONB DEFAULT '{}'
# After: merge retrieval_chunks into metadata alongside total_output_tokens
#
# Simplest approach: build metadata dict in Python before INSERT
metadata_obj = {}
if retrieval_chunks:
    metadata_obj["retrieval_chunks"] = retrieval_chunks

# Then in the SQL, merge with existing metadata rather than replacing
```

Note: The current `log_session()` doesn't write to the `metadata` column — token tracking in `throttle.py` writes there separately. Store retrieval_chunks in a new top-level JSONB key so it doesn't conflict.

### main.py

Destructure the new return from `chat()` and pass `chunk_meta` to `log_session()`.

### Testing

After a `/chat` request, query `chat_sessions` for the session and verify `metadata->'retrieval_chunks'` contains an array of chunk objects with `chunk_id`, `score`, `chunk_type`.

---

## A2 — Langfuse Integration `[Observability]`

### Rationale

No tracing exists. Every LLM call (main chat, input guardrail, output guardrail, photo classifier) is a black box. Langfuse provides request-level traces with latency, token usage, and score tracking — free tier, self-hostable, MIT-licensed.

### Files

- `backend/app/tracing.py` — **NEW FILE**
- `backend/app/orchestrator.py`
- `backend/app/guardrails.py`
- `backend/app/config.py`
- `requirements.txt`

### New file: tracing.py

```python
"""Langfuse tracing for HairGPT.

Provides a get_langfuse() singleton and helper decorators
for wrapping orchestrator steps in spans.
"""
import os
import logging
from contextlib import asynccontextmanager
from langfuse import Langfuse

logger = logging.getLogger(__name__)

_langfuse: Langfuse | None = None

def get_langfuse() -> Langfuse | None:
    global _langfuse
    public_key = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
    if not public_key:
        return None  # Tracing disabled — no-op in dev
    if _langfuse is None:
        _langfuse = Langfuse(
            public_key=public_key,
            secret_key=os.environ.get("LANGFUSE_SECRET_KEY", ""),
            host=os.environ.get("LANGFUSE_HOST", ""),  # Self-hosted Cloud Run URL
        )
    return _langfuse
```

### orchestrator.py — trace wrapping

Wrap the `chat()` function body in a Langfuse trace. Create child spans for each step:

| Span | Wraps | Metadata |
|------|-------|----------|
| `retrieval` | `retrieve()` call | query, top_k, chunk_meta from A1 |
| `input_guardrail` | `check_input()` | verdict, latency, user_message preview |
| `generation` | `client.aio.models.generate_content()` | model, temperature, token counts |
| `tool_execution` | `_execute_tool()` loop | tool name, args, result summary |
| `output_guardrail` | `check_output()` | verdict, latency |

Pattern for each span:

```python
langfuse = get_langfuse()
trace = langfuse.trace(
    name="chat",
    session_id=session_id,  # from the caller — see main.py change below
    metadata={"hair_context": hair_context},
) if langfuse else None

# For each step:
span = trace.span(name="retrieval", input={"query": user_message}) if trace else None
chunks = await retrieve(user_message, top_k=5)
retrieval_context, chunk_meta = format_retrieval_context(chunks)
if span:
    span.end(output={"chunk_count": len(chunks), "chunks": chunk_meta})
```

**Important:** The `chat()` function currently has no `session_id` parameter — it receives only `user_message` and `history`. Add `session_id: str = ""` as a parameter so traces can be grouped by session. Update the call in `main.py` to pass `session_id`.

### Graceful degradation

If `LANGFUSE_PUBLIC_KEY` is empty, `get_langfuse()` returns `None` and all `if trace` / `if span` guards skip tracing. Zero overhead when disabled. No exception paths.

### config.py

Add environment variables:

```python
langfuse_public_key: str = ""
langfuse_secret_key: str = ""
langfuse_host: str = ""  # Self-hosted Cloud Run URL
```

### requirements.txt

```
langfuse>=2.0
```

### Testing

Set Langfuse env vars to a test project. Send a `/chat` request. Verify a trace appears in the Langfuse dashboard with child spans for each step. Verify traces without env vars produce no errors.

---

## A3 — Guardrail Health Monitoring `[Observability]`

### Rationale

The output guardrail's false-positive rate is unknown. Before any relaxation can be considered (user's directive: "measure first"), we need structured logging of every verdict with enough context to audit.

### Files

- `backend/app/guardrails.py`

### guardrails.py changes

**check_input() — line 77:**

Add timing and structured log. After the LLM call returns:

```python
import time

async def check_input(user_message: str, history: list[dict] | None = None) -> tuple[bool, str]:
    start = time.monotonic()
    try:
        # ... existing LLM call ...
        result = (resp.text or "").strip()
        latency_ms = int((time.monotonic() - start) * 1000)

        verdict = "BLOCK" if result.startswith("BLOCK:") else "ALLOW"
        logger.info(
            "guardrail.input | verdict=%s | latency_ms=%d | msg_preview=%.80s",
            verdict, latency_ms, user_message,
        )

        if result.startswith("BLOCK:"):
            redirect_msg = result[6:].strip() or "I'm all about hair care! Got a hair question for me?"
            return False, redirect_msg
        return True, ""
    except Exception:
        latency_ms = int((time.monotonic() - start) * 1000)
        logger.exception("guardrail.input | verdict=ERROR | latency_ms=%d", latency_ms)
        return True, ""
```

**check_output() — line 157:**

Same pattern: add timing, structured log with verdict, latency, and previews of both user message and response.

```python
async def check_output(response_text: str, user_message: str) -> tuple[bool, str]:
    start = time.monotonic()
    try:
        # ... existing LLM call ...
        verdict = (resp.text or "").strip().upper()
        latency_ms = int((time.monotonic() - start) * 1000)

        logger.info(
            "guardrail.output | verdict=%s | latency_ms=%d | msg=%.80s | resp=%.120s",
            verdict, latency_ms, user_message, response_text,
        )

        if verdict == "FAIL":
            return False, _OUTPUT_FALLBACK
        return True, response_text
    except Exception:
        latency_ms = int((time.monotonic() - start) * 1000)
        logger.exception("guardrail.output | verdict=ERROR | latency_ms=%d", latency_ms)
        return True, response_text
```

If A2 (Langfuse) is in place, also end the guardrail span with the verdict and latency as output metadata.

### Testing

Send an off-topic message ("write me a Python script"). Verify structured log line appears with `verdict=BLOCK`. Send a normal hair question. Verify `verdict=ALLOW`. Check that latency values are populated.

---

## A4 — Engagement-Aware Token Budget `[Observability]`

### Rationale

The 15,000 output-token budget has a hard cut with no warning. Genuine users asking educative questions ("why do I need a leave-in?", "what does DCLOS do?") who then move to the recommendation flow shouldn't feel throttled. But users wasting the bot's time with off-topic or circular messages should get nudged to wrap up. The solution: classify engagement quality and apply different budget thresholds.

### Files

- `backend/app/throttle.py`
- `backend/app/orchestrator.py`
- `backend/app/prompts.py`

### throttle.py

**Add after line 19:**

```python
# Engaged users (educative questions, progressing toward recommendation)
# get generous thresholds — they should never feel throttled
ENGAGED_WARNING_RATIO = 0.88
ENGAGED_CRITICAL_RATIO = 0.95

# Disengaged users (no progress, off-topic, circular) get tighter limits
DEFAULT_WARNING_RATIO = 0.70
DEFAULT_CRITICAL_RATIO = 0.90


async def get_budget_status(session_id: str, is_engaged: bool = True) -> dict:
    """Return budget status, adjusting thresholds for engaged users.

    Engaged users asking genuine questions about products, ingredients,
    and routine mechanics get generous room. Users going in circles
    or wasting tokens on off-topic chat get earlier wrap-up nudges.
    """
    used = await get_session_tokens(session_id)
    limit = MAX_SESSION_TOKENS
    ratio = used / limit if limit > 0 else 0
    remaining = max(0, limit - used)

    warning_ratio = ENGAGED_WARNING_RATIO if is_engaged else DEFAULT_WARNING_RATIO
    critical_ratio = ENGAGED_CRITICAL_RATIO if is_engaged else DEFAULT_CRITICAL_RATIO

    if ratio >= 1.0:
        status = "exceeded"
    elif ratio >= critical_ratio:
        status = "critical"
    elif ratio >= warning_ratio:
        status = "warning"
    else:
        status = "ok"

    return {
        "status": status,
        "used": used,
        "limit": limit,
        "remaining": remaining,
        "is_engaged": is_engaged,
    }
```

### orchestrator.py

Import `get_budget_status` from throttle. Before building the system prompt, determine engagement quality from conversation state, then fetch budget status:

```python
# After: hair_context = _extract_hair_context(user_message, history)
# Add:
from app.throttle import get_budget_status

# --- Determine engagement quality ---
# A session is "engaged" if it shows genuine progress:
# - Has gathered at least 1 trait (hair type or concern identified)
# - OR a recommendation has been made (recommend_routine was called)
# - OR the user has uploaded a photo
# A session is "disengaged" if:
# - High message count (>6 turns) with no traits gathered
# - AND no recommendation made
# This is checked from hair_context and session state.
has_traits = bool(hair_context and (
    hair_context.get("hair_type") or
    hair_context.get("primary_concern")
))
has_recommendation = any(
    msg.get("role") == "model" and "recommend_routine" in str(msg.get("tool_calls", ""))
    for msg in (history or [])
)
has_photo = bool(hair_context and hair_context.get("photo_analysis"))
message_count = len([m for m in (history or []) if m.get("role") == "user"])

is_engaged = has_traits or has_recommendation or has_photo or message_count <= 6

budget = await get_budget_status(session_id, is_engaged=is_engaged)
system_prompt = build_system_prompt(
    retrieval_context,
    hair_context=hair_context,
    budget_status=budget["status"],
)
```

This requires `chat()` to receive `session_id` — same change as A2. If A2 isn't implemented yet, add the parameter here.

### prompts.py

In `build_system_prompt()`, add `budget_status: str = "ok"` parameter. The prompt nudges the model toward efficiency without making the user feel cut off:

```python
def build_system_prompt(
    retrieval_context: str,
    hair_context: dict | None = None,
    budget_status: str = "ok",
) -> str:
    prompt = SYSTEM_PROMPT
    # ... existing hair_context block ...
    # ... existing retrieval_context block ...

    if budget_status == "warning":
        prompt += (
            "\n\n## Session Note\n"
            "This session's token budget is running low. "
            "Be concise. If you haven't recommended a routine yet, "
            "move to recommendation now. If you have, offer a clear "
            "summary and mention support@moxiebeauty.in for follow-up."
        )
    elif budget_status == "critical":
        prompt += (
            "\n\n## Session Note\n"
            "This is likely the last response in this session. "
            "Give a clear, complete answer. End with: "
            "\"For more help, reach out to support@moxiebeauty.in "
            "or start a fresh chat!\""
        )

    return prompt
```

**Key design decision:** The user never sees "you're running out of time" messaging. The budget status is injected into the *system prompt* only — it changes how the model structures its response (more concise, drives toward recommendation), not what the user perceives. A genuine user asking educative questions barely hits "warning" at all because of the 88% threshold, and if they do, the model simply becomes tighter without announcing it.

### Testing

**Engaged path:** Simulate a session where the user asks "what does a leave-in conditioner do?" then "why do curls need a gel?", provides hair type, gets a recommendation. Set `total_output_tokens` to 11,000 (73%). Verify budget status returns `"ok"` — the engaged threshold (88%) hasn't been hit.

**Disengaged path:** Simulate a session with 8 messages, no traits gathered, no recommendation, no photo. Set tokens to 11,000 (73%). Verify budget status returns `"warning"` — the default threshold (70%) applies.

**Invisible throttling:** In both cases, verify the user's response contains no language about limits, budgets, or running out of time. The model's behavior shifts subtly (more concise, drives toward recommendation), but the user never sees a warning.

---

## B1 — Start Small + Novice Detection `[Conversation]`

### Rationale

Multi-product routines overwhelm novice users. Presenting routines in phases — foundation first, enhancement second — matches how real habit adoption works. Users with established routines get the full picture. The bot decides which path to take based on conversational signals during trait gathering.

### Files

- `backend/app/recommendations.py`
- `backend/app/orchestrator.py`
- `backend/app/prompts.py`

### Cohort Definitions (reference — drives all changes below)

| Cohort | Trigger | Foundation | Enhancement |
|--------|---------|------------|-------------|
| **Styling** | primary_concern is wave_definition or curl_definition | Styling products (leave-in/cream + gel). *If user also wants wash*: add shampoo + conditioner to foundation. | Mention GCS + UHC as supporting note: "These work best when cleansing and conditioning are part of the routine — our Gentle Cleansing Shampoo and Ultra Hydrating Conditioner work really well with this." |
| **Concern** | primary_concern is scalp | ScalpSOS wash trio (Pre-Wash Treatment as hero) | Daily Calming Leave-On Serum — "Once the flaking calms down, this keeps it that way." |
| **Combined** | has_scalp_concern=true AND concern is wave/curl_definition | Scalp products first — "Healthy scalp is the foundation for good styling." | Styling products with trial sizes — "Once your scalp is happy, this is where definition comes from." |
| **General** | All other concerns | Wash products | Treatment products (serum, mask) if applicable |

### recommendations.py

#### 1. Add trial size mappings (top of file, after product line constants)

```python
# Trial sizes for "Start Small" enhancement phase
SAMPLER_MAP = {
    "weightless-leave-in-conditioner": "weightless-leave-in-conditioner-sampler",
    "flexi-styling-serum-gel": "flexi-styling-serum-gel-sampler",
    "super-defining-curl-cream": "super-defining-curl-cream-sampler",
    "gentle-cleansing-shampoo": "gentle-cleansing-shampoo-sampler",
    "ultra-hydrating-conditioner": "ultra-hydrating-conditioner-sampler",
}

TRAVEL_MAP = {
    "weightless-leave-in-conditioner": "weightless-leave-in-conditioner-travel-size",
    "flexi-styling-serum-gel": "flexi-styling-serum-gel-travel-size",
    "super-defining-curl-cream": "super-defining-curl-cream-travel-size",
    "gentle-cleansing-shampoo": "gentle-cleansing-shampoo-travel-size",
    "ultra-hydrating-conditioner": "ultra-hydrating-conditioner-travel-size",
}

SAMPLER_SET_MAP = {
    "wavy": "moxie-wavy-sampler-set",
    "curly": "moxie-curly-sampler-set",
}

TRAVEL_ROUTINE_MAP = {
    "wavy": "the-moxie-wavy-travel-routine",
    "curly": "the-moxie-curly-travel-routine",
}
```

#### 2. Add trial option helper

**Samplers are free at checkout.** They're added by the user during Shopify checkout — HairGPT informs users about the free sampler option verbally but does NOT add sampler cards to the product carousel. Travel sizes (50ml, ₹265–295) are the carousel trial option.

```python
def _get_trial_option(handle: str) -> dict | None:
    """Find trial-size variants for a product.

    Returns a dict with:
    - travel: travel-size info for carousel display (50ml, ₹265-295)
    - sampler: sampler info for verbal mention only (10ml, ₹0, free at checkout)

    Samplers are NOT shown in the carousel — they're free add-ons at checkout
    and the bot mentions them conversationally.
    """
    result = {}

    # Travel size — goes into carousel as a purchasable trial option
    travel_h = TRAVEL_MAP.get(handle)
    if travel_h and travel_h in PRODUCT_CATALOG:
        info = PRODUCT_CATALOG[travel_h]
        price = info.get("price", "")
        if price and price not in ("₹0", "Rs. 0.00", ""):
            result["travel"] = {
                "handle": travel_h,
                "name": info.get("name", travel_h),
                "price": price,
                "url": info.get("url", ""),
                "image": info.get("image_src", ""),
            }

    # Sampler — verbal mention only ("you can add a free sampler at checkout")
    sampler_h = SAMPLER_MAP.get(handle)
    if sampler_h and sampler_h in PRODUCT_CATALOG:
        info = PRODUCT_CATALOG[sampler_h]
        result["sampler"] = {
            "handle": sampler_h,
            "name": info.get("name", sampler_h),
            "price": "Free",
        }

    return result if result else None
```

#### 3. Modify recommend_routine() signature

```python
def recommend_routine(
    hair_type: str = "2A",
    formation: str = "wavy",
    texture: str = "medium",
    primary_concern: str = "general_care",
    has_frizz: bool = False,
    is_chemically_treated: bool = False,
    is_colored: bool = False,
    has_scalp_concern: bool = False,
    user_experience: str = "novice",       # NEW
    wants_wash: bool = True,                # NEW — styling-only override
) -> dict:
```

#### 4. Add phase tagging after step assembly (before the return)

The existing logic builds `steps` in two phases: Phase 1 (wash) and Phase 2 (style/treat). For novice users, tag steps and determine the cohort:

```python
    # --- Determine cohort ---
    is_styling_concern = primary_concern in ("wave_definition", "curl_definition", "style")
    is_scalp_primary = has_scalp_concern and primary_concern == "scalp"

    if is_scalp_primary and is_styling_concern:
        cohort = "combined"
    elif is_scalp_primary:
        cohort = "concern"
    elif is_styling_concern:
        cohort = "styling"
    else:
        cohort = "general"

    # --- Phase tagging for novice users ---
    if user_experience == "novice":
        for step in steps:
            step["phase"] = "foundation"  # default

        if cohort == "styling":
            # Styling products are foundation; wash is supporting
            for step in steps:
                if step["handle"] in [h for h, _, _ in WASH_GENTLE + WASH_HYDROREPAIR + WASH_SCALP]:
                    if not wants_wash:
                        step["phase"] = "supporting"  # mentioned, not in carousel
                    # If wants_wash, wash stays foundation
                else:
                    step["phase"] = "foundation"  # styling = foundation
        elif cohort == "concern":
            # Wash trio = foundation; DCLOS = enhancement
            for step in steps:
                if step.get("optional"):
                    step["phase"] = "enhancement"
        elif cohort == "combined":
            # Scalp wash = foundation; styling = enhancement
            style_handles = [h for h, _, _ in STYLE_WAVY + STYLE_CURLY + TREAT_FRIZZ]
            for step in steps:
                if step["handle"] in style_handles:
                    step["phase"] = "enhancement"
        else:
            # General: wash = foundation; serums/treatments = enhancement
            treat_handles = [h for h, _, _ in TREAT_FRIZZ + TREAT_HYDROREPAIR_SERUM + TREAT_SCALP_SERUM]
            for step in steps:
                if step["handle"] in treat_handles:
                    step["phase"] = "enhancement"

        # Attach trial options to enhancement steps
        # travel → carousel display; sampler → verbal mention by model
        for step in steps:
            if step.get("phase") == "enhancement":
                trial = _get_trial_option(step["handle"])
                if trial:
                    step["trial_option"] = trial
    else:
        # Experienced: no phasing
        for step in steps:
            step["phase"] = "full"
        cohort = "full"
```

#### 5. Update the return dict

```python
    return {
        "routine": routine_label,
        "steps": steps,
        "reasoning": reasoning,
        "total_steps": len(steps),
        "user_experience": user_experience,
        "cohort": cohort,
        "inputs": {
            "hair_type": hair_type,
            "formation": formation,
            "texture": texture,
            "primary_concern": primary_concern,
            "has_frizz": has_frizz,
            "is_chemically_treated": is_chemically_treated,
            "is_colored": is_colored,
            "has_scalp_concern": has_scalp_concern,
        },
    }
```

### orchestrator.py — tool schema

**Add to recommend_routine parameters (after has_scalp_concern, line 67):**

```python
                    "user_experience": types.Schema(
                        type="STRING",
                        enum=["novice", "experienced"],
                        description=(
                            "User's hair routine experience level. "
                            "'novice' = no established routine or single-product routine. "
                            "'experienced' = has multi-step routine with specific named products. "
                            "Default to 'novice' unless strong experienced signals observed."
                        ),
                    ),
                    "wants_wash": types.Schema(
                        type="BOOLEAN",
                        description=(
                            "For styling-focused users: whether they also want wash recommendations. "
                            "True if they mentioned wanting a complete routine including wash. "
                            "False if they only asked about styling/definition products."
                        ),
                    ),
```

**Update _execute_tool() to pass new params:**

```python
    return recommend_routine(
        hair_type=args.get("hair_type", "2A"),
        formation=args.get("formation", "wavy"),
        texture=args.get("texture", "medium"),
        primary_concern=concern,
        has_frizz=args.get("has_frizz", False),
        is_chemically_treated=args.get("is_chemically_treated", False),
        is_colored=args.get("is_colored", False),
        has_scalp_concern=has_scalp,
        user_experience=args.get("user_experience", "novice"),
        wants_wash=args.get("wants_wash", True),
    )
```

### prompts.py — system prompt additions

**Add after the "## ─── CONVERSATION FLOW ───" section (after line 57):**

```
## User Experience Assessment
During conversation, assess if the user is NOVICE or EXPERIENCED with hair routines.

EXPERIENCED — user demonstrates ALL of these:
- Has a current multi-step routine (names products or categories)
- Shows familiarity with product types (knows what a leave-in does, etc.)

NOVICE (default) — ANY of these:
- No current routine, or "I just use shampoo"
- Asks what a product type does ("what's a leave-in?")
- Single-product routine
- Vague descriptions without product specificity
- First time exploring textured hair care

An informed user who knows terminology but has NO established routine is NOVICE.
The test is: do they have a routine habit to build on?

Pass user_experience to recommend_routine based on your assessment.
```

**Replace the "## ─── RECOMMENDATION RULES ───" routine presentation section (lines 152-184):**

```
## ─── RECOMMENDATION RULES ───
When you call recommend_routine and get results back:

### For NOVICE users (phased presentation)
The routine will come back with steps tagged as "foundation", "enhancement", or "supporting".
Present them in two layers:

**Layer 1 — "Your Foundation"**
Present foundation products with a one-line "why" for each. These go in the product carousel.

**Layer 2 — "Your Next Step"**
Present enhancement products as what to explore once the foundation is working.
If a step has trial_option.travel, mention the travel size: "Try the travel size (50ml, [price]) to see how it works for you."
If a step has trial_option.sampler, mention: "You can also add a free 10ml sampler at checkout to try it before committing."
Samplers are free at checkout — they do NOT appear in the product carousel. Only travel sizes appear as carousel cards.

**Styling cohort (user wants curl/wave definition):**
- If wants_wash=false: Lead with styling products as foundation. Then add:
  "These styling products work best when your hair is properly cleansed and conditioned.
  Our Gentle Cleansing Shampoo and Ultra Hydrating Conditioner work really well among our customers with [wavy/curly] hair."
- If wants_wash=true: Wash as foundation, styling with trial sizes as next step.

**Concern cohort (dandruff/scalp):**
- Foundation: ScalpSOS trio. Call out the Pre-Wash Treatment as the hero product.
- Next step: "Once the flaking calms down, the Daily Calming Leave-On Serum keeps it that way."

**Combined cohort (scalp + styling):**
- Foundation: Scalp products — "Healthy scalp is the foundation for good styling."
- Next step: Styling products with trial sizes — "Once your scalp feels better, this is where definition comes from."

### For EXPERIENCED users
Present the full routine without phasing. They know their way around.

### Options after recommendation
Novice: OPTIONS: Add foundation to cart|Tell me more about [hero enhancement product]|Show me the full routine
Experienced: OPTIONS: Build my personalised cart|How do I use these?|Try something different

If a novice clicks "Show me the full routine", present all products without phasing.
```

### Prompt version bump

In `prompt_versions.py`: bump `SYSTEM_PROMPT_VERSION` to `"2.0.0"`, `TOOLS_VERSION` to `"2.0.0"`, `RECOMMENDATIONS_VERSION` to `"2.0.0"`.

### Testing

**Novice styling path:** Say "hi, I have wavy 2B hair and want to define my waves." Verify: routine presents styling products as foundation, wash as a supporting mention with GCS + UHC names. Trial sizes appear for styling products.

**Novice dandruff path:** Say "I have dandruff and itchy scalp." After providing hair type, verify: ScalpSOS trio as foundation, DCLOS as next step with trial option.

**Experienced path:** Say "I currently use the Gentle Cleansing Shampoo and UHC but want to add curl definition for my 3A hair." Verify: full routine presented without phasing.

**Styling-only:** Say "I just want something for curl definition, I already have my wash sorted." Verify: only styling products in carousel, wash mentioned as supporting text, NOT as products to buy.

---

## B2 — adjust_routine Tool `[Conversation]`

### Rationale

When users want to modify a recommendation ("can I swap the shampoo?", "add something for my scalp too"), the bot currently has to re-call `recommend_routine` from scratch with no compatibility checking. A dedicated tool surfaces incompatibilities before the routine is presented.

### Files

- `backend/app/orchestrator.py`
- `backend/app/recommendations.py`
- `backend/app/prompts.py`

### recommendations.py — new function

```python
def _check_compatibility(formation: str, steps: list[dict]) -> list[str]:
    """Check for product incompatibilities in a routine."""
    warnings = []
    handles = [s["handle"] for s in steps]

    # Frizz serum only for straight / 2A
    if "frizz-fighting-hair-serum" in handles and formation in ("curly",):
        warnings.append(
            "Frizz Fighting Serum isn't designed for curly routines — "
            "it can weigh down curl definition. Consider the styling duo instead."
        )
    if "frizz-fighting-hair-serum" in handles and formation == "wavy":
        # 2A is OK, 2B/2C should use styling instead
        warnings.append(
            "For wavier patterns (2B/2C), the Wavy Vibe Setter duo "
            "handles frizz AND definition. The serum is best for straighter textures."
        )

    # HA serum + styling conflict
    ha_present = "hyaluronic-acid-hair-serum" in handles
    styling_present = any(
        h in handles for h in
        ["weightless-leave-in-conditioner", "super-defining-curl-cream", "flexi-styling-serum-gel"]
    )
    if ha_present and styling_present:
        warnings.append(
            "HA Serum can't be layered with leave-in or curl cream — "
            "it weighs down texture. Your HydroRepair wash already delivers repair."
        )

    return warnings


def adjust_routine(
    current_inputs: dict,
    adjustment_type: str,
    new_concern: str | None = None,
) -> dict:
    """Adjust a previously recommended routine.

    adjustment_type: 'change_concern', 'add_scalp', 'drop_scalp',
                     'swap_to_gentle', 'swap_to_hydrorepair', 'swap_to_scalp'
    """
    inputs = dict(current_inputs)

    if adjustment_type == "change_concern" and new_concern:
        inputs["primary_concern"] = new_concern
    elif adjustment_type == "add_scalp":
        inputs["has_scalp_concern"] = True
    elif adjustment_type == "drop_scalp":
        inputs["has_scalp_concern"] = False
    elif adjustment_type == "swap_to_gentle":
        inputs["primary_concern"] = "general_care"
        inputs["is_chemically_treated"] = False
        inputs["is_colored"] = False
    elif adjustment_type == "swap_to_hydrorepair":
        inputs["primary_concern"] = "damage_repair"
    elif adjustment_type == "swap_to_scalp":
        inputs["has_scalp_concern"] = True

    result = recommend_routine(**inputs)

    # Run compatibility check on the assembled routine
    warnings = _check_compatibility(inputs.get("formation", "wavy"), result["steps"])
    if warnings:
        result["compatibility_warnings"] = warnings

    result["adjusted_from"] = current_inputs
    return result
```

### orchestrator.py — tool declaration

Add to the `TOOLS` list after the `get_product` declaration:

```python
types.FunctionDeclaration(
    name="adjust_routine",
    description=(
        "Adjust a previously recommended routine when the user wants to swap "
        "a product line, add/remove a concern, or change focus. "
        "Includes product compatibility checks. "
        "Use INSTEAD of re-calling recommend_routine when modifying an existing recommendation."
    ),
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "adjustment_type": types.Schema(
                type="STRING",
                enum=[
                    "change_concern", "add_scalp", "drop_scalp",
                    "swap_to_gentle", "swap_to_hydrorepair", "swap_to_scalp",
                ],
                description="Type of adjustment to make to the current routine",
            ),
            "new_concern": types.Schema(
                type="STRING",
                enum=[
                    "frizz_control", "wave_definition", "curl_definition",
                    "damage_repair", "scalp", "style", "general_care",
                ],
                description="New primary concern (only for change_concern adjustment)",
            ),
            "current_hair_type": types.Schema(type="STRING", description="Hair type from previous recommendation"),
            "current_formation": types.Schema(type="STRING", enum=["straight", "wavy", "curly"]),
            "current_texture": types.Schema(type="STRING", enum=["fine", "medium", "coarse"]),
            "current_concern": types.Schema(type="STRING", description="Previous primary concern"),
            "current_has_scalp": types.Schema(type="BOOLEAN", description="Previous scalp flag"),
            "current_is_treated": types.Schema(type="BOOLEAN", description="Previous chemical treatment flag"),
            "current_is_colored": types.Schema(type="BOOLEAN", description="Previous color flag"),
        },
        required=["adjustment_type", "current_hair_type", "current_formation", "current_texture", "current_concern"],
    ),
),
```

**Update _execute_tool():**

```python
    if name == "adjust_routine":
        current_inputs = {
            "hair_type": args.get("current_hair_type", "2A"),
            "formation": args.get("current_formation", "wavy"),
            "texture": args.get("current_texture", "medium"),
            "primary_concern": args.get("current_concern", "general_care"),
            "has_scalp_concern": args.get("current_has_scalp", False),
            "is_chemically_treated": args.get("current_is_treated", False),
            "is_colored": args.get("current_is_colored", False),
        }
        return adjust_routine(
            current_inputs=current_inputs,
            adjustment_type=args.get("adjustment_type", "change_concern"),
            new_concern=args.get("new_concern"),
        )
```

### prompts.py

Add after "Handling 'try something different'" section:

```
### Using adjust_routine
When the user wants to MODIFY the current recommendation (not start over):
- "Can I swap the shampoo?" → adjust_routine with swap_to_gentle/hydrorepair/scalp
- "Add something for my scalp too" → adjust_routine with add_scalp
- "Actually I want curl definition instead" → adjust_routine with change_concern

If adjust_routine returns compatibility_warnings, present them educationally:
explain WHY the combination doesn't work and what the alternative achieves.
Do NOT just say "incompatible" — teach the user something.

Keep using recommend_routine (not adjust_routine) when:
- This is the FIRST recommendation in the conversation
- The user wants a completely different direction ("start over")
```

### Testing

Get a wavy routine recommendation. Then say "can you add something for my scalp too?" Verify adjust_routine is called with `add_scalp`, and the returned routine includes ScalpSOS products. Say "what about the frizz serum?" for a 3B curly user — verify a compatibility warning about frizz serum not suiting curly routines.

---

## B3 — Post-Rec Education `[Conversation]`

### Rationale

The recommendation-to-ATC gap is partly a confidence gap. Users don't understand WHY these specific products were chosen for THEIR hair. A brief educational hook after the routine presentation builds the confidence to act.

### Files

- `backend/app/prompts.py`

### prompts.py addition

Add after the routine presentation rules:

```
### Post-recommendation education
After presenting the routine, add ONE educational line about the hero product's
mechanism — WHY it works for this specific hair type and concern. This must be
grounded in Moxie's product science (from the knowledge base), not generic claims.

Examples (adapt to concern):
- Frizz: "The serum gel works because it forms a flexible film that blocks humidity
  — that's what causes frizz to spring back between washes."
- Curls: "The curl cream's hold comes from a polymer blend that clumps curls together
  without making them crunchy. Your 3A pattern holds definition longer with this weight."
- Scalp: "The Pre-Wash Treatment has Piroctone Olamine — it targets the fungus that
  causes dandruff, not just the flakes. That's why improvement compounds over 2-3 washes."
- Damage: "HydroRepair's hyaluronic acid binds water inside the hair shaft, not just
  on the surface. That's why it feels different from a regular moisturizing shampoo."

RULES:
- ONE line only (fits within 60-word response limit alongside the routine)
- Must be from the knowledge base — NEVER invent mechanisms or clinical claims
- Connect to THEIR specific hair type/concern, not generic
- If no specific mechanism is available in the knowledge base, skip this
```

### Testing

Request a curly routine. Verify the response includes a brief mechanism line about why the curl cream works for their pattern. Verify the educational claim exists in the CX handbook chunks. Verify total response stays under 60 words (or is split across a natural follow-up).

---

## B4 — Tradeoff Education `[Conversation]`

### Rationale

When users ask "why not X product?" or "what about the HA serum?", the bot needs to explain the tradeoff specifically for their hair type — not a generic "it's not compatible." This builds trust and positions Moxie as an educator.

### Files

- `backend/app/prompts.py`

### prompts.py addition

Add after the post-rec education section:

```
### Handling tradeoff questions
When a user asks "why not [product]?" or "what about [product]?" after a recommendation:

1. Acknowledge the product is good — never dismiss it
2. Explain the specific tradeoff for THEIR hair: what it would do well and what
   it would compromise
3. Reaffirm why the recommended product fits their specific combination better

Example tradeoffs to handle educationally:
- "Why not the HA serum?" (for wavy/curly user): "The HA serum is excellent for deep
  repair — but it's a leave-in that competes with your styling products for the same
  slot. Layering both can weigh down your waves/curls and reduce definition. Your
  HydroRepair wash is already delivering the repair benefits during the wash itself."
- "Why not the frizz serum?" (for curly user): "The Frizz Fighting Serum works by
  smoothing the cuticle — perfect for straighter textures. For your curls, that
  smoothing effect would flatten your natural pattern. The curl cream gives you
  frizz control AND definition."

RULES:
- Never say "it's incompatible" without explaining the mechanism
- Always relate back to THEIR specific hair type and concern
- Be honest if both products could work — suggest they try the alternative as a
  Phase 2 experiment after their current routine is established
```

### Testing

Get a wavy routine recommendation. Ask "what about the HA serum instead?" Verify the response explains the layering tradeoff specific to wavy hair, not a generic incompatibility message.

---

## B5 — Opening Message Update `[Conversation]`

### Rationale

The current opening doesn't prime users for photo upload or set the right expectation. The update removes generic "we're here to help" language and leads with the photo CTA.

### Files

- `backend/static/moxiebuddy-widget.js`

### Widget JS change

Find the initial greeting message in the widget (search for the hardcoded opening message string — likely near the `initChat` or `startConversation` function). Replace with:

```
"Hey! I'm HairGPT — your hair-care sidekick 🧴 Let's start by seeing your hair! Upload a photo and I'll figure out your exact hair type and the right products for you."
```

The initial OPTIONS should remain:

```
["Upload a photo of my hair", "I need a routine", "I have a product question"]
```

**Note:** The widget JS is 333KB minified. Search for the existing greeting text string to locate the exact edit point. Do not refactor surrounding code — change only the string.

### Testing

Load the widget preview (`/preview` endpoint). Verify the opening message matches the new text. Verify the three option buttons appear below it.

---

## B6 — MoxieBuddy → HairGPT Rename `[Conversation]`

### Rationale

The chatbot is called "HairGPT" in all user-facing contexts but "MoxieBuddy" persists in the codebase — widget file name, system prompt persona, CSS class names, and internal references. This creates confusion and brand inconsistency. Rename throughout.

### Files

- `backend/static/moxiebuddy-widget.js`
- `backend/app/prompts.py`
- `backend/app/main.py`
- `backend/templates/` (if any)
- Shopify theme snippet

### Scope

This is a search-and-replace across the codebase. The key targets:

| Location | What changes |
|----------|-------------|
| `backend/static/moxiebuddy-widget.js` | Rename file to `hairgpt-widget.js`. Replace all internal string references to "MoxieBuddy" with "HairGPT". Update CSS class prefixes from `.moxiebuddy-` to `.hairgpt-`. |
| `backend/app/prompts.py` | Replace "MoxieBuddy" in the system prompt persona line (line ~3: "You are MoxieBuddy…") with "You are HairGPT…" |
| `backend/app/main.py` | Update any static file paths referencing `moxiebuddy-widget.js` |
| Shopify theme | Update the `<script>` tag that loads the widget JS from the new filename |

### Approach

```bash
# 1. Find all references
grep -ri "moxiebuddy" backend/ data/ infra/ --include="*.py" --include="*.js" --include="*.html" --include="*.json"

# 2. Rename the widget file
mv backend/static/moxiebuddy-widget.js backend/static/hairgpt-widget.js

# 3. Replace string references (case-insensitive sweep, then verify each)
# In prompts.py: "MoxieBuddy" → "HairGPT"
# In widget JS: "MoxieBuddy" → "HairGPT" (user-facing strings)
# CSS classes: ".moxiebuddy-" → ".hairgpt-" (internal, no user impact)

# 4. Update the Shopify snippet to load the renamed file
```

**Note:** The widget JS is 333KB minified. Use exact string matching, not regex. Test the widget loads after renaming — the Shopify snippet's script `src` attribute must match the new filename.

### Testing

After rename: load the widget via `/preview`. Verify the opening message says "HairGPT", not "MoxieBuddy". Verify the widget renders and functions — styling, chat, photo upload. Grep the codebase for any remaining "MoxieBuddy" references.

---

## C1 — Tutorial Overhaul `[Content]`

### Rationale

The current tutorial flow is agentic — the bot describes the video and provides a URL. This works but misses the opportunity for inline video rendering. Additionally, the prompt should guide tutorial suggestions more proactively after recommendations.

### Files

- `backend/app/prompts.py`

### prompts.py update

Replace the existing "## Video tutorials" section (lines 223–234) with:

```
## Video tutorials
The widget auto-embeds YouTube Shorts URLs into an inline video player.
When presenting a tutorial, put the URL on its own line — this triggers the embed.

### When to suggest tutorials:
1. After a routine recommendation — "Want to see how to use these? I have a quick tutorial!"
2. When the user asks "how do I use it?" or "how do I use these?"
3. When the user seems unsure about application technique

### How to present:
- Share the YouTube URL from the knowledge base, NEVER a Google Drive link
- Add a one-line context before the URL: what they'll learn
- The URL must be on its own line for the widget to embed it

### Routine-to-tutorial mapping:
- Wavy routine → Wavy Hair Routine Tutorial
- Curly routine → Curly Hair Routine Tutorial
- Frizz routine (straight) → Ditch the Frizz Trio Tutorial
- Dry shampoo → Dry Shampoo Tutorial
- Heat protection → Heat Protection Spray Tutorial
- Flyaways/finishing → OTF Hair Finishing Stick Tutorial

### Gender-aware tutorials
If the user's gender is known (from photo analysis), prefer gender-matched tutorials
when available. Default to female tutorials if unknown.

### IMPORTANT
- Do NOT call recommend_routine when the user asks for a tutorial
- Only share YouTube URLs from the knowledge base — NEVER fabricate URLs
- If no matching tutorial exists, give concise text-based instructions
```

### Testing

Get a wavy routine recommendation, then ask "how do I use these?" Verify the bot suggests the Wavy Hair Routine Tutorial with the correct YouTube URL on its own line. Verify it does NOT re-call recommend_routine.

---

## C2 — Video Chunk Expansion `[Content]`

### Rationale

The YouTube playlist now has 9 videos but only 6 are indexed. The 3 missing videos need to be added to `video_chunks.json` and ingested into the KB.

### Files

- `data/video_chunks.json`
- `infra/ingest script (if exists)`

### Current indexed videos

| Video | YouTube ID | Status |
|-------|-----------|--------|
| Wavy Hair Routine | Sp2t61IXhMU | Indexed |
| Curly Hair Routine | gaUNgPn9M70 | Indexed |
| Ditch the Frizz Trio | yJ2T7PMhS_M | Indexed |
| Dry Shampoo | SP9BL_IWmhk | Indexed |
| OTF Finishing Stick | Ex-wM4vzxew | Indexed |
| Heat Protection Spray | jrcc8MzktN4 | Indexed |
| *3 videos from playlist not yet indexed* | — | Missing |

### Action

Fetch the playlist at `https://youtube.com/playlist?list=PLrvigBLzpOnb7W8o4PC6W2SkmKRYyyD96` to identify the 3 missing videos. For each, create a chunk entry following the existing format in `video_chunks.json`:

```json
{
  "content": "Tutorial video: [Title]\n\n[Description]\n\nWatch here: [YouTube URL]\n\nProducts featured: [handles]\n\nRoutine: [routine_key]\n\nBest for hair types: [types]",
  "source_type": "video_tutorial",
  "source_url": "[YouTube URL]",
  "source_id": "video_[YouTube ID]",
  "chunk_type": "video_tutorial",
  "topic_tags": [...],
  "product_refs": [...],
  "hair_types": [...],
  "metadata": {
    "public_url": "[YouTube URL]",
    "title": "[Title]",
    "youtube_id": "[ID]"
  }
}
```

After adding to the JSON file, the chunks need to be embedded and inserted into `kb_chunks`. Check if an ingest script exists in the codebase; if not, write a one-off script that reads `video_chunks.json`, generates embeddings via `text-embedding-005`, and inserts into the table.

### Testing

After ingestion, query the KB for "how to use curly cream" or "scalp treatment tutorial" and verify the newly indexed videos appear in retrieval results with appropriate scores.

---

## Deployment

All 12 changes ship in a single deployment. The observability layer (A1–A4) is what makes this safe — Langfuse traces, guardrail health logs, and chunk tracking give per-change visibility from the first request, so each experiment's impact can be isolated in the data without needing separate deploy cycles.

| Workstream | Items | What Langfuse tracks |
|-----------|-------|---------------------|
| **Observability** | A1, A2, A3, A4 | Chunk retrieval scores, guardrail verdicts + latency, budget status per session, engagement classification |
| **Conversation** | B1, B2, B3, B4, B5, B6 | Tool calls show `user_experience` and `cohort` on every `recommend_routine` call; `adjust_routine` calls + compatibility warnings; post-rec education presence in output |
| **Content** | C1, C2 | Video tutorial chunk retrieval frequency; tutorial URL presence in responses |

Bump all changed `prompt_versions.py` constants in one go. The version fingerprint on every trace cleanly separates pre-sprint and post-sprint behavior in Langfuse dashboards.

---

## Version Bumps Summary

In `backend/app/prompt_versions.py`, update all changed constants in the single deployment:

| Constant | Current | After Sprint 1 | Reason |
|----------|---------|----------------|--------|
| `SYSTEM_PROMPT_VERSION` | 1.1.0 | 2.0.0 | Novice detection, phased presentation, education, tutorials, budget, rename |
| `INPUT_GUARDRAIL_VERSION` | 1.0.0 | 1.0.0 | Unchanged — logging only, no prompt change |
| `OUTPUT_GUARDRAIL_VERSION` | 1.0.0 | 1.0.0 | Unchanged — logging only |
| `CLASSIFIER_VERSION` | 1.1.0 | 1.1.0 | Unchanged |
| `TOOLS_VERSION` | 1.0.0 | 2.0.0 | New params on recommend_routine, new adjust_routine tool |
| `RECOMMENDATIONS_VERSION` | 1.0.0 | 2.0.0 | Phased steps, cohort logic, trial options, compatibility checks |

---

## Environment & Configuration

### Self-hosted Langfuse on Cloud Run

Langfuse runs alongside HairGPT on Cloud Run, sharing the existing Cloud SQL infrastructure.

#### Langfuse service dependencies

| Component | What | Notes |
|-----------|------|-------|
| **Docker image** | `langfuse/langfuse:2` | Single container — includes web UI, API, and worker. Deploy as a Cloud Run service. |
| **PostgreSQL** | Separate database on existing Cloud SQL instance | Create a `langfuse` database on the same Cloud SQL instance HairGPT uses. Langfuse manages its own schema via migrations on startup. |
| **Auth seed** | `NEXTAUTH_SECRET`, `SALT` | Random 32-char strings. Generate once, store in Secret Manager. |

#### Langfuse Cloud Run env vars

```
# Required for Langfuse server
DATABASE_URL=postgresql://langfuse_user:****@/langfuse?host=/cloudsql/PROJECT:REGION:INSTANCE
NEXTAUTH_SECRET=<random-32-char>
SALT=<random-32-char>
NEXTAUTH_URL=https://langfuse-XXXXXX.run.app   # Langfuse's own Cloud Run URL
TELEMETRY_ENABLED=false
```

#### Cost

Langfuse on Cloud Run with 0 min-instances and auto-scaling: essentially free at current HairGPT traffic levels. Storage is in the shared Cloud SQL instance — Langfuse's trace data is lightweight (JSON spans, not embeddings).

### HairGPT env vars (new)

| Variable | Required | Default | Notes |
|----------|----------|---------|-------|
| `LANGFUSE_PUBLIC_KEY` | No | *empty* | Tracing disabled when empty. Generate from Langfuse UI after first deploy. |
| `LANGFUSE_SECRET_KEY` | No | *empty* | Pair with public key |
| `LANGFUSE_HOST` | No | *empty* | Self-hosted Langfuse Cloud Run URL, e.g. `https://langfuse-XXXXXX.run.app` |

### HairGPT Python dependencies (new)

| Package | Version | Purpose |
|---------|---------|---------|
| `langfuse` | >=2.0 | Python SDK — sends traces to self-hosted Langfuse instance |

### Database changes

**HairGPT database:** None. All new data (chunk metadata, budget status) uses the existing `metadata` JSONB column on `chat_sessions`. No schema migration needed.

**Langfuse database:** New database `langfuse` on existing Cloud SQL instance. Langfuse handles its own migrations on container startup — no manual SQL needed.

---

*HairGPT Sprint 1 Implementation Plan — September 2026. 12 changes, single deployment. Built for execution by Claude Code against the current codebase at `backend/app/`.*
