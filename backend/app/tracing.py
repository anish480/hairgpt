"""Langfuse tracing for HairGPT.

Provides a get_langfuse() singleton and helpers for wrapping orchestrator
steps in spans. Tracing is disabled (no-op) when LANGFUSE_PUBLIC_KEY is empty.
"""

import os
import logging

from langfuse import Langfuse

logger = logging.getLogger(__name__)

_langfuse: Langfuse | None = None


def get_langfuse() -> Langfuse | None:
    global _langfuse
    public_key = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
    if not public_key:
        return None
    if _langfuse is None:
        _langfuse = Langfuse(
            public_key=public_key,
            secret_key=os.environ.get("LANGFUSE_SECRET_KEY", ""),
            host=os.environ.get("LANGFUSE_HOST", ""),
        )
    return _langfuse
