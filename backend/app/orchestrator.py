import json
import re

from google.genai import types

from app.llm import _client, FLASH
from app.prompts import build_system_prompt
from app.recommendations import recommend_routine, get_product
from app.retrieval import retrieve, format_retrieval_context

TOOLS = types.Tool(
    function_declarations=[
        types.FunctionDeclaration(
            name="recommend_routine",
            description=(
                "Get the recommended Moxie product routine based on hair attributes and goals. "
                "Call this when the user has shared enough about their hair type and what they need."
            ),
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "hair_pattern": types.Schema(
                        type="STRING",
                        enum=["straight", "wavy", "curly", "coily"],
                        description="User's hair pattern category",
                    ),
                    "primary_goal": types.Schema(
                        type="STRING",
                        enum=[
                            "frizz_control",
                            "wave_definition",
                            "curl_definition",
                            "damage_repair",
                            "general_care",
                        ],
                        description="User's primary hair goal",
                    ),
                    "is_chemically_treated": types.Schema(
                        type="BOOLEAN",
                        description="Whether hair is chemically treated (straightened, permed, keratin, etc.)",
                    ),
                    "is_colored": types.Schema(
                        type="BOOLEAN",
                        description="Whether hair is colour-treated",
                    ),
                },
                required=["hair_pattern", "primary_goal"],
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
        return recommend_routine(
            hair_pattern=args.get("hair_pattern", "wavy"),
            primary_goal=args.get("primary_goal", "general_care"),
            is_chemically_treated=args.get("is_chemically_treated", False),
            is_colored=args.get("is_colored", False),
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


async def chat(
    user_message: str,
    history: list[dict] | None = None,
) -> tuple[str, list[dict]]:
    history = history or []

    chunks = await retrieve(user_message, top_k=5)
    retrieval_context = format_retrieval_context(chunks)
    system_prompt = build_system_prompt(retrieval_context)

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

    display_text, suggested_options = _parse_options(response_text)

    updated_history = history + [
        {"role": "user", "content": user_message},
        {"role": "assistant", "content": display_text},
    ]

    return display_text, updated_history, suggested_options


def _parse_options(text: str) -> tuple[str, list[str]]:
    match = re.search(r"\n?OPTIONS:\s*(.+?)$", text, re.MULTILINE)
    if not match:
        return text, []
    options = [o.strip() for o in match.group(1).split("|") if o.strip()]
    display_text = text[: match.start()].rstrip()
    return display_text, options
