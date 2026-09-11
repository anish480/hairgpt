"""Langfuse tracing for HairGPT.

Provides a get_langfuse() singleton and helpers for wrapping orchestrator
steps in spans. Tracing is disabled (no-op) when LANGFUSE_PUBLIC_KEY is empty
or when the installed SDK version is incompatible.
"""

import os
import logging

from langfuse import Langfuse

logger = logging.getLogger(__name__)

_langfuse: Langfuse | None = None
_checked = False


def get_langfuse() -> Langfuse | None:
    global _langfuse, _checked
    if _checked:
        return _langfuse
    public_key = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
    if not public_key:
        _checked = True
        return None
    try:
        lf = Langfuse(
            public_key=public_key,
            secret_key=os.environ.get("LANGFUSE_SECRET_KEY", ""),
            host=os.environ.get("LANGFUSE_HOST", ""),
        )
        if not hasattr(lf, "trace"):
            logger.warning("Langfuse SDK missing .trace() — tracing disabled (upgrade to langfuse<3)")
            _checked = True
            return None
        _langfuse = lf
    except Exception:
        logger.exception("Failed to init Langfuse — tracing disabled")
    _checked = True
    return _langfuse
