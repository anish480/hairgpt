from functools import lru_cache

from google import genai
from google.genai import types

from app.config import settings

FLASH = "gemini-2.5-flash"
PRO = "gemini-2.5-pro"


@lru_cache(maxsize=1)
def _client() -> genai.Client:
    return genai.Client(
        vertexai=True,
        project=settings.gcp_project_id,
        location=settings.gcp_location,
    )


async def generate(
    prompt: str,
    model: str = FLASH,
    max_tokens: int = 1024,
    thinking_budget: int | None = None,
) -> str:
    cfg = types.GenerateContentConfig(max_output_tokens=max_tokens)
    if thinking_budget is not None:
        cfg.thinking_config = types.ThinkingConfig(thinking_budget=thinking_budget)

    resp = await _client().aio.models.generate_content(
        model=model,
        contents=prompt,
        config=cfg,
    )
    return resp.text or ""
