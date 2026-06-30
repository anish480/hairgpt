"""Rate limiting and session token budget enforcement.

- Rate limit: 10 requests per minute per session (sliding window in memory).
- Token budget: 15,000 output tokens per session (tracked in DB).
"""

from __future__ import annotations

import json
import logging
import time
from collections import defaultdict

from app.db import get_pool

logger = logging.getLogger(__name__)

MAX_REQUESTS_PER_MINUTE = 10
MAX_SESSION_TOKENS = 15_000
_WINDOW_SECONDS = 60

_request_log: dict[str, list[float]] = defaultdict(list)


def check_rate_limit(session_id: str) -> bool:
    """Return True if the request is within rate limits."""
    now = time.monotonic()
    cutoff = now - _WINDOW_SECONDS
    timestamps = _request_log[session_id]
    _request_log[session_id] = [t for t in timestamps if t > cutoff]
    if len(_request_log[session_id]) >= MAX_REQUESTS_PER_MINUTE:
        logger.warning("Rate limit hit for session %s", session_id)
        return False
    _request_log[session_id].append(now)
    return True


async def get_session_tokens(session_id: str) -> int:
    """Get total output tokens used by a session."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchval(
                "SELECT COALESCE((metadata->>'total_output_tokens')::int, 0) "
                "FROM chat_sessions WHERE session_id = $1",
                session_id,
            )
            return row or 0
    except Exception:
        logger.exception("Failed to read session tokens for %s", session_id)
        return 0


async def check_token_budget(session_id: str) -> bool:
    """Return True if session is within token budget."""
    used = await get_session_tokens(session_id)
    if used >= MAX_SESSION_TOKENS:
        logger.warning(
            "Token budget exceeded for session %s: %d/%d",
            session_id, used, MAX_SESSION_TOKENS,
        )
        return False
    return True


async def record_tokens(session_id: str, output_tokens: int) -> None:
    """Add output_tokens to the session's running total."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            updated = await conn.execute(
                """
                UPDATE chat_sessions
                SET metadata = jsonb_set(
                    COALESCE(metadata, '{}'::jsonb),
                    '{total_output_tokens}',
                    (COALESCE((metadata->>'total_output_tokens')::int, 0) + $2)::text::jsonb
                )
                WHERE session_id = $1
                """,
                session_id,
                output_tokens,
            )
            if updated == "UPDATE 0":
                await conn.execute(
                    """
                    INSERT INTO chat_sessions (session_id, metadata)
                    VALUES ($1, $2::jsonb)
                    ON CONFLICT (session_id) DO UPDATE
                    SET metadata = jsonb_set(
                        COALESCE(chat_sessions.metadata, '{}'::jsonb),
                        '{total_output_tokens}',
                        (COALESCE((chat_sessions.metadata->>'total_output_tokens')::int, 0) + $3)::text::jsonb
                    )
                    """,
                    session_id,
                    json.dumps({"total_output_tokens": output_tokens}),
                    output_tokens,
                )
    except Exception:
        logger.exception("Failed to record tokens for session %s", session_id)
