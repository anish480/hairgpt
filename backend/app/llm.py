import json
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


EMBED_MODEL = "text-embedding-005"
EMBED_DIM = 768


async def embed(texts: list[str]) -> list[list[float]]:
    result = await _client().aio.models.embed_content(
        model=EMBED_MODEL,
        contents=texts,
        config=types.EmbedContentConfig(output_dimensionality=EMBED_DIM),
    )
    return [e.values for e in result.embeddings]


async def embed_batch(texts: list[str], batch_size: int = 20) -> list[list[float]]:
    all_embs: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        all_embs.extend(await embed(texts[i : i + batch_size]))
    return all_embs


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


CLASSIFY_PROMPT = """\
Analyze this hair photo and classify the hair attributes. \
Look at the curl/wave pattern, frizz level, visible damage, length, and any porosity indicators. \
If the image is not clearly a hair photo or is too blurry, set confidence to "low" \
and hair_pattern to "unable_to_determine". \
Be honest about uncertainty — it's better to say "unable_to_determine" than guess wrong."""

HAIR_CLASSIFICATION_SCHEMA = types.Schema(
    type="OBJECT",
    properties={
        "hair_pattern": types.Schema(
            type="STRING",
            enum=["straight", "wavy", "curly", "coily", "unable_to_determine"],
        ),
        "hair_pattern_code": types.Schema(
            type="STRING",
            enum=["1a", "1b", "1c", "2a", "2b", "2c", "3a", "3b", "3c", "4a", "4b", "4c", "unknown"],
        ),
        "frizz_level": types.Schema(
            type="STRING", enum=["none", "mild", "moderate", "severe"],
        ),
        "damage_signs": types.Schema(
            type="STRING", enum=["none", "mild", "moderate", "severe"],
        ),
        "length": types.Schema(
            type="STRING", enum=["short", "medium", "long", "very_long"],
        ),
        "confidence": types.Schema(
            type="STRING", enum=["high", "medium", "low"],
        ),
        "notes": types.Schema(type="STRING"),
    },
    required=[
        "hair_pattern", "hair_pattern_code", "frizz_level",
        "damage_signs", "length", "confidence", "notes",
    ],
)


async def classify_hair_photo(image_bytes: bytes, mime_type: str) -> dict:
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=HAIR_CLASSIFICATION_SCHEMA,
        max_output_tokens=512,
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )
    resp = await _client().aio.models.generate_content(
        model=FLASH,
        contents=types.Content(
            role="user",
            parts=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                types.Part.from_text(text=CLASSIFY_PROMPT),
            ],
        ),
        config=config,
    )
    return json.loads(resp.text)


def format_classification_summary(result: dict) -> str:
    pattern = result.get("hair_pattern", "unknown")
    code = result.get("hair_pattern_code", "unknown")
    frizz = result.get("frizz_level", "unknown")
    damage = result.get("damage_signs", "unknown")
    length = result.get("length", "unknown")
    confidence = result.get("confidence", "unknown")
    notes = result.get("notes", "")

    parts = []
    if pattern != "unable_to_determine":
        code_str = f" (around {code.upper()})" if code != "unknown" else ""
        parts.append(f"you have {pattern} hair{code_str}")
    else:
        parts.append("I couldn't clearly determine your hair type from this photo")

    if frizz != "none":
        parts.append(f"{frizz} frizz")
    if damage != "none":
        parts.append(f"{damage} damage signs")

    parts.append(f"{length} length")

    summary = "Based on your photo, " + ", ".join(parts) + "."
    if confidence == "low":
        summary += " (Note: I'm not very confident in this assessment — the photo may not show your hair clearly enough.)"
    if notes:
        summary += f" {notes}"
    return summary
