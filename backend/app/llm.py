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
You are a professional hair texture analyst trained in the Paul Mitchell hair typing system.

INPUT
You will receive a single image of a person's hair. First assess image quality, then classify.

STEP 1 — IMAGE QUALITY ASSESSMENT
Before classifying, check if the image is usable:
- "good": hair is clearly visible, in focus, adequate lighting — proceed to classify.
- "blurry": image is out of focus or motion-blurred — hair texture unreadable.
- "poor_lighting": too dark, overexposed, or heavy light aberration — hair detail lost.
- "no_hair_visible": no hair in frame, face-only, object, or unrelated image.
- "obscured": hair is tied up, covered by hat/scarf, or cropped out.

If image_quality is anything other than "good", set classifiable to false and leave
classification fields at their default values. The system will ask the user for a better photo.

STEP 2 — HAIR CLASSIFICATION (only when image_quality is "good")

The Paul Mitchell system describes hair using two independent axes:
- FORMATION — the natural curl or wave pattern (row number 1–3)
- TEXTURE — the thickness of a single individual strand (column letter A–C)

Combined, this gives 9 categories: 1A, 1B, 1C, 2A, 2B, 2C, 3A, 3B, 3C.

TYPE 1 — STRAIGHT
- Hair hangs straight with no repeating S-wave. May have body/bends but NO rhythmic S-wave.
- 1A: pin-straight, no volume. 1B: straight with body/movement. 1C: coarser, slight bend at ends.

TYPE 2 — WAVY
- Clear open S-shaped pattern. Never closes into a loop.
- 2A: loose mid-shaft waves. 2B: defined S-waves from mid-length. 2C: strong S-waves from root.

STRAIGHT vs WAVY TIEBREAK: When unsure between straight and wavy → choose 1B.

TYPE 3 — CURLY
- Definite closed loops, ringlets, or spirals. Pattern is circular/corkscrew.
- 3A: loose ringlets (~chalk diameter). 3B: springy ringlets (~marker diameter).
- 3C: tight corkscrews (~pencil diameter).

SHORT-HAIR RULES: Diameter scale does not apply to short hair. Only call curly if you see
a CLOSED loop. Bends/open S = wavy. If too short to confirm → set classifiable to false.

TEXTURE:
- A (fine): barely visible strands, lies flat, silky.
- B (medium): moderate width, balanced volume. Default when strands visible but unclear.
- C (coarse): visibly thick/stiff strands, high natural volume.

CLASSIFICATION RULES:
- Hair color and gender NEVER affect classification.
- If hair appears heat-styled, classify by root texture and set hair_state to "heat_styled".
- Frizz, styling, and product do NOT change the fundamental type.

CRITICAL RULES:
- Wavy = REPEATING open S-wave visible. Not body, not bends, not volume.
- Curly = at least one FULLY CLOSED loop confirmed. Open S no matter how tight = wavy.
- 2C vs 3B: 2C is open S; 3B is closed coil. When cannot confirm closed coil → call 2C.

FRIZZ (separate from hair type):
- none: clean silhouette, zero escaped strands, shine visible.
- low: mostly clean edge, 1–5 flyaways at hairline/ends only.
- medium: soft/blurred edge, 5–20 escaped strands, matte in places.
- high: visible halo, 20+ floating strands, pattern broken down, fully matte.

HAIR STATE:
- "natural_dry": dry, natural state — most reliable for classification.
- "wet_damp": wet/damp hair — classification less reliable.
- "heat_styled": flat-ironed/blow-dried — classify by root texture.
- "product_styled": gel/wax/mousse visible.

Return ONLY raw JSON, no markdown, no backticks."""

CLASSIFY_PROMPT_FORCE = CLASSIFY_PROMPT + """

IMPORTANT OVERRIDE: This is the user's second attempt. Even if image quality is imperfect,
do your BEST to classify the hair. Set classifiable to true and provide your best estimate.
Only set classifiable to false if you genuinely cannot see any hair at all."""

HAIR_CLASSIFICATION_SCHEMA = types.Schema(
    type="OBJECT",
    properties={
        "image_quality": types.Schema(
            type="STRING",
            enum=["good", "blurry", "poor_lighting", "no_hair_visible", "obscured"],
        ),
        "classifiable": types.Schema(type="BOOLEAN"),
        "gender": types.Schema(
            type="STRING",
            enum=["Male", "Female", "Unknown"],
        ),
        "formation": types.Schema(
            type="STRING",
            enum=["straight", "wavy", "curly", "indeterminate"],
        ),
        "hair_type": types.Schema(
            type="STRING",
            enum=["1A", "1B", "1C", "2A", "2B", "2C", "3A", "3B", "3C", "indeterminate"],
        ),
        "texture": types.Schema(
            type="STRING",
            enum=["fine", "medium", "coarse"],
        ),
        "frizz": types.Schema(
            type="STRING",
            enum=["none", "low", "medium", "high"],
        ),
        "hair_state": types.Schema(
            type="STRING",
            enum=["natural_dry", "wet_damp", "heat_styled", "product_styled"],
        ),
        "quality_note": types.Schema(type="STRING"),
    },
    required=[
        "image_quality", "classifiable", "gender", "formation",
        "hair_type", "texture", "frizz", "hair_state",
    ],
)

RETRY_MESSAGES = {
    "blurry": "Your photo seems a bit blurry — could you take another one with steadier hands and good lighting? That'll help me read your hair texture accurately!",
    "poor_lighting": "The lighting in your photo makes it hard to see your hair clearly. Could you try again in natural light or a well-lit room?",
    "no_hair_visible": "I can't quite see your hair in this photo. Could you send one that shows your hair clearly — ideally loose and from the side or back?",
    "obscured": "It looks like your hair is tied up or covered. For the best analysis, could you send a photo with your hair down and visible?",
}


async def classify_hair_photo(image_bytes: bytes, mime_type: str, is_retry: bool = False) -> dict:
    prompt = CLASSIFY_PROMPT_FORCE if is_retry else CLASSIFY_PROMPT
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=HAIR_CLASSIFICATION_SCHEMA,
        max_output_tokens=1024,
        thinking_config=types.ThinkingConfig(thinking_budget=2048),
    )
    resp = await _client().aio.models.generate_content(
        model=FLASH,
        contents=types.Content(
            role="user",
            parts=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                types.Part.from_text(text=prompt),
            ],
        ),
        config=config,
    )
    raw = json.loads(resp.text)

    if not raw.get("classifiable", False):
        quality = raw.get("image_quality", "blurry")
        raw["needs_retry"] = not is_retry
        raw["retry_message"] = RETRY_MESSAGES.get(quality, RETRY_MESSAGES["blurry"])
    else:
        raw["needs_retry"] = False
        confidence = "high" if raw.get("hair_state") == "natural_dry" else "medium"
        raw["confidence"] = confidence

    return raw


def format_classification_summary(result: dict) -> str:
    if result.get("needs_retry"):
        return result.get("retry_message", "Could you try sending another photo?")

    hair_type = result.get("hair_type", "indeterminate")
    formation = result.get("formation", "indeterminate")
    texture = result.get("texture", "medium")
    frizz = result.get("frizz", "none")
    confidence = result.get("confidence", "low")

    if hair_type == "indeterminate" or not result.get("classifiable"):
        return "I couldn't clearly determine your hair type from this photo. Could you try again with a clearer shot of your hair in its natural state?"

    gender = result.get("gender", "Unknown")
    parts = [f"you have {formation} hair (type {hair_type})"]
    parts.append(f"{texture} texture")
    if frizz != "none":
        parts.append(f"{frizz} frizz")

    summary = "Based on your photo, " + ", ".join(parts) + "."
    if gender and gender != "Unknown":
        summary += f" [gender:{gender}]"
    if confidence != "high":
        summary += " For a more accurate reading, try a photo of your hair in its natural, dry state."
    return summary
