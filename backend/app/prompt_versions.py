"""Prompt and guardrail versioning.

Every versionable component (system prompt, guardrails, classifier, tools,
generation params) gets a version constant. The bundle of all active versions
is stamped onto each chat session for before/after comparison.
"""

from __future__ import annotations

import hashlib
import json
import logging

from app.db import get_pool

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_VERSION = "2.0.0"
INPUT_GUARDRAIL_VERSION = "1.0.0"
OUTPUT_GUARDRAIL_VERSION = "1.0.0"
CLASSIFIER_VERSION = "1.1.0"
TOOLS_VERSION = "2.0.0"
RECOMMENDATIONS_VERSION = "2.0.0"

GENERATION_PARAMS = {
    "chat": {"model": "gemini-2.5-flash", "temperature": 0.7, "max_output_tokens": 1024, "thinking_budget": 0},
    "input_guardrail": {"model": "gemini-2.5-flash", "temperature": 0.0, "max_output_tokens": 100, "thinking_budget": 0},
    "output_guardrail": {"model": "gemini-2.5-flash", "temperature": 0.0, "max_output_tokens": 5, "thinking_budget": 0},
    "classifier": {"model": "gemini-2.5-flash", "thinking_budget": 2048},
}


def get_version_bundle() -> dict:
    return {
        "system_prompt": SYSTEM_PROMPT_VERSION,
        "input_guardrail": INPUT_GUARDRAIL_VERSION,
        "output_guardrail": OUTPUT_GUARDRAIL_VERSION,
        "classifier": CLASSIFIER_VERSION,
        "tools": TOOLS_VERSION,
        "recommendations": RECOMMENDATIONS_VERSION,
        "generation_params": GENERATION_PARAMS,
    }


def get_bundle_fingerprint() -> str:
    bundle = get_version_bundle()
    raw = json.dumps(bundle, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


async def register_version_if_new() -> str:
    """Register the current version bundle in prompt_versions table if not already present."""
    fingerprint = get_bundle_fingerprint()
    bundle = get_version_bundle()
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            existing = await conn.fetchval(
                "SELECT fingerprint FROM prompt_versions WHERE fingerprint = $1",
                fingerprint,
            )
            if not existing:
                await conn.execute(
                    """
                    INSERT INTO prompt_versions (fingerprint, version_bundle, created_at)
                    VALUES ($1, $2, NOW())
                    ON CONFLICT (fingerprint) DO NOTHING
                    """,
                    fingerprint,
                    json.dumps(bundle),
                )
                logger.info("Registered new prompt version: %s", fingerprint)
    except Exception:
        logger.exception("Failed to register prompt version %s", fingerprint)
    return fingerprint
