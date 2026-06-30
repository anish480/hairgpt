import json
import re

from google.genai import types

from app.guardrails import check_input, check_output
from app.llm import _client, FLASH
from app.prompts import build_system_prompt
from app.recommendations import recommend_routine, get_product
from app.retrieval import retrieve, format_retrieval_context

TOOLS = types.Tool(
    function_declarations=[
        types.FunctionDeclaration(
            name="recommend_routine",
            description=(
                "Build a personalised Moxie product routine based on the customer's hair traits and concerns. "
                "Call this ONLY after you know their hair type AND primary concern. "
                "The routine is assembled from composable product lines — wash, style, treat — "
                "tailored to the customer's specific combination of needs."
            ),
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "hair_type": types.Schema(
                        type="STRING",
                        description="Paul Mitchell hair type code, e.g. '1A', '2B', '3C'",
                    ),
                    "formation": types.Schema(
                        type="STRING",
                        enum=["straight", "wavy", "curly"],
                        description="Hair formation pattern",
                    ),
                    "texture": types.Schema(
                        type="STRING",
                        enum=["fine", "medium", "coarse"],
                        description="Individual strand thickness",
                    ),
                    "primary_concern": types.Schema(
                        type="STRING",
                        enum=[
                            "frizz_control",
                            "wave_definition",
                            "curl_definition",
                            "damage_repair",
                            "scalp",
                            "style",
                            "general_care",
                        ],
                        description="The customer's primary hair concern",
                    ),
                    "has_frizz": types.Schema(
                        type="BOOLEAN",
                        description="Whether the customer has frizz (from photo or self-report)",
                    ),
                    "is_chemically_treated": types.Schema(
                        type="BOOLEAN",
                        description="Whether hair is chemically treated (straightened, permed, keratin, smoothening)",
                    ),
                    "is_colored": types.Schema(
                        type="BOOLEAN",
                        description="Whether hair is colour-treated",
                    ),
                    "has_scalp_concern": types.Schema(
                        type="BOOLEAN",
                        description="Whether the customer mentioned scalp issues (dandruff, itching, flakes)",
                    ),
                },
                required=["hair_type", "formation", "texture", "primary_concern"],
            ),
        ),
        types.FunctionDeclaration(
            name="get_product",
            description=(
                "Get details (name, price, link) for a specific Moxie product by its handle. "
                "Use when the user asks about a specific product."
            ),
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "product_handle": types.Schema(
                        type="STRING",
                        description=(
                            "Moxie product handle, e.g. 'gentle-cleansing-shampoo', "
                            "'super-defining-curl-cream', 'frizz-fighting-hair-serum'"
                        ),
                    ),
                },
                required=["product_handle"],
            ),
        ),
    ]
)


def _execute_tool(name: str, args: dict) -> dict:
    if name == "recommend_routine":
        concern = args.get("primary_concern", "general_care")
        has_scalp = args.get("has_scalp_concern", False)
        if concern == "scalp":
            has_scalp = True
        return recommend_routine(
            hair_type=args.get("hair_type", "2A"),
            formation=args.get("formation", "wavy"),
            texture=args.get("texture", "medium"),
            primary_concern=concern,
            has_frizz=args.get("has_frizz", False),
            is_chemically_treated=args.get("is_chemically_treated", False),
            is_colored=args.get("is_colored", False),
            has_scalp_concern=has_scalp,
        )
    if name == "get_product":
        return get_product(args.get("product_handle", ""))
    return {"error": f"Unknown tool: {name}"}


def _history_to_contents(history: list[dict]) -> list[types.Content]:
    contents = []
    for msg in history:
        role = msg["role"]
        if role == "assistant":
            role = "model"
        contents.append(
            types.Content(role=role, parts=[types.Part.from_text(text=msg["content"])])
        )
    return contents


def _extract_hair_context(user_message: str, history: list[dict]) -> dict | None:
    """Extract hair classification context injected by the widget from photo analysis."""
    for text in [user_message] + [m.get("content", "") for m in history]:
        if "[User uploaded a hair photo. Analysis:" in text or "[Hair photo analysis:" in text:
            ctx = {"photo_uploaded": True}
            text_lower = text.lower()
            for formation in ("straight", "wavy", "curly"):
                if formation in text_lower:
                    ctx["formation"] = formation
                    break
            for code in ("1A", "1B", "1C", "2A", "2B", "2C", "3A", "3B", "3C"):
                if code in text or code.lower() in text_lower:
                    ctx["hair_type"] = code
                    break
            for texture in ("fine", "medium", "coarse"):
                if texture in text_lower:
                    ctx["texture"] = texture
                    break
            for frizz in ("high", "medium", "low"):
                if f"{frizz} frizz" in text_lower:
                    ctx["frizz"] = frizz
                    break
            if "[gender:Male]" in text:
                ctx["gender"] = "Male"
            elif "[gender:Female]" in text:
                ctx["gender"] = "Female"
            return ctx
    return None


async def chat(
    user_message: str,
    history: list[dict] | None = None,
) -> tuple[str, list[dict], list[str], dict | None]:
    history = history or []

    is_photo_context = "[User uploaded a hair photo" in user_message or "[Hair photo analysis:" in user_message
    if not is_photo_context:
        allowed, redirect_msg = await check_input(user_message, history)
        if not allowed:
            updated_history = history + [
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": redirect_msg},
            ]
            return redirect_msg, updated_history, [], None, 0

    chunks = await retrieve(user_message, top_k=5)
    retrieval_context = format_retrieval_context(chunks)

    hair_context = _extract_hair_context(user_message, history)
    system_prompt = build_system_prompt(retrieval_context, hair_context=hair_context)

    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        tools=[TOOLS],
        temperature=0.7,
        max_output_tokens=1024,
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )

    contents = _history_to_contents(history)
    contents.append(
        types.Content(role="user", parts=[types.Part.from_text(text=user_message)])
    )

    client = _client()
    resp = await client.aio.models.generate_content(
        model=FLASH, contents=contents, config=config,
    )

    routine_data = None

    for _ in range(3):
        function_calls = [
            p for p in resp.candidates[0].content.parts if p.function_call
        ]
        if not function_calls:
            break

        contents.append(resp.candidates[0].content)
        tool_response_parts = []
        for fc in function_calls:
            result = _execute_tool(fc.function_call.name, dict(fc.function_call.args))
            if fc.function_call.name == "recommend_routine" and "error" not in result:
                routine_data = result
            tool_response_parts.append(
                types.Part.from_function_response(
                    name=fc.function_call.name, response=result
                )
            )
        contents.append(types.Content(parts=tool_response_parts))

        resp = await client.aio.models.generate_content(
            model=FLASH, contents=contents, config=config,
        )

    response_text = resp.text or ""

    output_tokens = 0
    if resp.usage_metadata:
        output_tokens = getattr(resp.usage_metadata, "candidates_token_count", 0) or 0

    display_text, suggested_options = _parse_options(response_text)

    is_safe, sanitized = await check_output(display_text, user_message)
    if not is_safe:
        display_text = sanitized
        suggested_options = ["I need a routine", "I have a product question", "Upload a photo of my hair"]

    updated_history = history + [
        {"role": "user", "content": user_message},
        {"role": "assistant", "content": display_text},
    ]

    return display_text, updated_history, suggested_options, routine_data, output_tokens


def _parse_options(text: str) -> tuple[str, list[str]]:
    match = re.search(r"\n?OPTIONS:\s*(.+?)$", text, re.MULTILINE)
    if not match:
        return text, []
    options = [o.strip() for o in match.group(1).split("|") if o.strip()]
    display_text = text[: match.start()].rstrip()
    return display_text, options
