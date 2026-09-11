import json
import re
import time

from google.genai import types

from app.guardrails import check_input, check_output
from app.llm import _client, FLASH
from app.prompts import build_system_prompt
from app.recommendations import recommend_routine, adjust_routine, get_product
from app.retrieval import retrieve, format_retrieval_context
from app.throttle import get_budget_status
from app.tracing import get_langfuse

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
            user_experience=args.get("user_experience", "novice"),
            wants_wash=args.get("wants_wash", True),
        )
    if name == "get_product":
        return get_product(args.get("product_handle", ""))
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
    session_id: str = "",
) -> tuple[str, list[dict], list[str], list[str], dict | None, int, list[dict]]:
    history = history or []

    langfuse = get_langfuse()
    trace = langfuse.trace(
        name="chat",
        session_id=session_id or None,
        input={"user_message": user_message[:200]},
    ) if langfuse else None

    is_photo_context = "[User uploaded a hair photo" in user_message or "[Hair photo analysis:" in user_message
    if not is_photo_context:
        ig_gen = trace.generation(
            name="input_guardrail",
            model=FLASH,
            model_parameters={"temperature": 0.0, "max_output_tokens": 100},
            input={"msg_preview": user_message[:80]},
        ) if trace else None
        ig_start = time.monotonic()
        allowed, redirect_msg = await check_input(user_message, history)
        if ig_gen:
            ig_gen.end(output={"verdict": "ALLOW" if allowed else "BLOCK"}, level="DEFAULT")
        if not allowed:
            if trace:
                trace.update(output={"blocked": True})
            updated_history = history + [
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": redirect_msg},
            ]
            return redirect_msg, updated_history, [], [], None, 0, []

    ret_span = trace.span(name="retrieval", input={"query": user_message[:200], "top_k": 5}) if trace else None
    chunks = await retrieve(user_message, top_k=5)
    retrieval_context, chunk_meta = format_retrieval_context(chunks)
    if ret_span:
        ret_span.end(output={"chunk_count": len(chunks), "chunks": chunk_meta})

    hair_context = _extract_hair_context(user_message, history)

    has_traits = bool(hair_context and (
        hair_context.get("hair_type") or
        hair_context.get("formation")
    ))
    has_recommendation = any(
        msg.get("role") == "assistant" and "recommend_routine" in str(msg.get("content", ""))
        for msg in history
    )
    has_photo = bool(hair_context and hair_context.get("photo_uploaded"))
    message_count = len([m for m in history if m.get("role") == "user"])
    is_engaged = has_traits or has_recommendation or has_photo or message_count <= 6

    budget = await get_budget_status(session_id, is_engaged=is_engaged) if session_id else {"status": "ok"}
    system_prompt = build_system_prompt(
        retrieval_context,
        hair_context=hair_context,
        budget_status=budget["status"],
    )

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
    gen_obs = trace.generation(
        name="generation",
        model=FLASH,
        model_parameters={"temperature": 0.7, "max_output_tokens": 1024},
        input={"message_count": len(contents)},
    ) if trace else None
    gen_start = time.monotonic()
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
            tool_span = trace.span(name="tool_execution", input={"tool": fc.function_call.name, "args": dict(fc.function_call.args)}) if trace else None
            result = _execute_tool(fc.function_call.name, dict(fc.function_call.args))
            if tool_span:
                tool_span.end(output={"tool": fc.function_call.name, "has_error": "error" in result})
            if fc.function_call.name in ("recommend_routine", "adjust_routine") and "error" not in result:
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

    if gen_obs:
        input_tokens = getattr(resp.usage_metadata, "prompt_token_count", 0) or 0
        total_tokens = getattr(resp.usage_metadata, "total_token_count", 0) or 0
        gen_obs.end(
            output=response_text[:500],
            usage={"input": input_tokens, "output": output_tokens, "total": total_tokens},
            metadata={"latency_ms": int((time.monotonic() - gen_start) * 1000)},
        )

    display_text, suggested_options, multi_select_options = _parse_options(response_text)

    display_text = _inject_missing_video_url(display_text, chunks)

    og_gen = trace.generation(
        name="output_guardrail",
        model=FLASH,
        model_parameters={"temperature": 0.0, "max_output_tokens": 5},
        input={"resp_preview": display_text[:120]},
    ) if trace else None
    og_start = time.monotonic()
    is_safe, sanitized = await check_output(display_text, user_message)
    if og_gen:
        og_gen.end(output={"verdict": "PASS" if is_safe else "FAIL"})
    if not is_safe:
        display_text = sanitized
        suggested_options = ["I need a routine", "I have a product question", "Upload a photo of my hair"]
        multi_select_options = []

    updated_history = history + [
        {"role": "user", "content": user_message},
        {"role": "assistant", "content": display_text},
    ]

    if trace:
        trace.update(output={"response_preview": display_text[:200], "output_tokens": output_tokens})

    return display_text, updated_history, suggested_options, multi_select_options, routine_data, output_tokens, chunk_meta


_YT_URL_RE = re.compile(r"https?://(?:www\.)?(?:youtube\.com/(?:shorts/|watch\?v=)|youtu\.be/)[\w-]{11}")


def _inject_missing_video_url(text: str, chunks: list) -> str:
    """If the model mentions a tutorial but forgot the YouTube URL, append it from retrieval."""
    text_lower = text.lower()
    mentions_video = any(w in text_lower for w in ("tutorial", "watch here", "watch it", "video"))
    if not mentions_video:
        return text
    if _YT_URL_RE.search(text):
        return text
    for chunk in chunks:
        if chunk.chunk_type == "video_tutorial":
            match = _YT_URL_RE.search(chunk.content)
            if match:
                return text.rstrip() + "\n\n" + match.group(0)
    return text


def _parse_options(text: str) -> tuple[str, list[str], list[str]]:
    multi_match = re.search(r"\n?MULTI_OPTIONS:\s*(.+?)$", text, re.MULTILINE)
    match = re.search(r"\n?(?<!MULTI_)OPTIONS:\s*(.+?)$", text, re.MULTILINE)

    multi_options: list[str] = []
    if multi_match:
        multi_options = [o.strip() for o in multi_match.group(1).split("|") if o.strip()]

    options: list[str] = []
    if match:
        options = [o.strip() for o in match.group(1).split("|") if o.strip()]

    cuts = sorted(
        [m.start() for m in (multi_match, match) if m],
        reverse=False,
    )
    if cuts:
        text = text[: cuts[0]].rstrip()

    return text, options, multi_options
