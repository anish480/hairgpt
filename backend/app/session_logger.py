"""Upsert conversation state into chat_sessions on every /chat call."""

from __future__ import annotations

import json
import logging
import re

from app.db import get_pool

logger = logging.getLogger(__name__)

_BASE64_PATTERN = re.compile(r"data:image/[^;]+;base64,[A-Za-z0-9+/=]{100,}")


def _sanitize_message(content: str) -> str:
    return _BASE64_PATTERN.sub("[Image Uploaded]", content)


def _sanitize_history(history: list[dict]) -> list[dict]:
    sanitized = []
    for msg in history:
        entry = {
            "role": msg.get("role", ""),
            "content": _sanitize_message(msg.get("content", "")),
        }
        sanitized.append(entry)
    return sanitized


async def log_session(
    session_id: str,
    history: list[dict],
    device_info: dict | None = None,
    ga_context: dict | None = None,
    hair_context: dict | None = None,
    routine_data: dict | None = None,
    photo_uploaded: bool = False,
) -> None:
    try:
        pool = await get_pool()
        sanitized = _sanitize_history(history)
        message_count = len([m for m in sanitized if m.get("role") == "user"])

        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO chat_sessions
                    (session_id, device_info, ga_context, conversation_log,
                     hair_context, routine_recommended, message_count,
                     photo_uploaded, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW(), NOW())
                ON CONFLICT (session_id) DO UPDATE SET
                    conversation_log = EXCLUDED.conversation_log,
                    hair_context = COALESCE(EXCLUDED.hair_context, chat_sessions.hair_context),
                    routine_recommended = COALESCE(EXCLUDED.routine_recommended, chat_sessions.routine_recommended),
                    message_count = EXCLUDED.message_count,
                    photo_uploaded = chat_sessions.photo_uploaded OR EXCLUDED.photo_uploaded,
                    device_info = COALESCE(EXCLUDED.device_info, chat_sessions.device_info),
                    ga_context = COALESCE(EXCLUDED.ga_context, chat_sessions.ga_context),
                    updated_at = NOW()
                """,
                session_id,
                json.dumps(device_info or {}),
                json.dumps(ga_context or {}),
                json.dumps(sanitized),
                json.dumps(hair_context or {}),
                json.dumps(routine_data) if routine_data else None,
                message_count,
                photo_uploaded,
            )
    except Exception:
        logger.exception("Failed to log chat session %s", session_id)
