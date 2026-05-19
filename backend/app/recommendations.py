import json
from pathlib import Path

_CATALOG_PATH = Path(__file__).resolve().parents[2] / "data" / "product_catalog.json"


def _load_catalog() -> dict[str, dict]:
    if _CATALOG_PATH.exists():
        with open(_CATALOG_PATH) as f:
            return json.load(f)
    return {}


PRODUCT_CATALOG = _load_catalog()

RECOMMENDATION_RULES = [
    {
        "match": {"is_chemically_treated": True},
        "routine": "HydroRepair Routine",
        "products": [
            "hyaluronic-acid-repairing-shampoo",
            "hyaluronic-acid-repairing-conditioner",
            "hyaluronic-acid-repairing-serum",
        ],
        "reason": "Damage repair priority for chemically treated hair",
    },
    {
        "match": {"is_colored": True, "primary_goal": "damage_repair"},
        "routine": "HydroRepair Routine",
        "products": [
            "hyaluronic-acid-repairing-shampoo",
            "hyaluronic-acid-repairing-conditioner",
            "hyaluronic-acid-repairing-serum",
        ],
        "reason": "Damage repair for coloured hair",
    },
    {
        "match": {"hair_pattern": "wavy", "primary_goal": "wave_definition"},
        "routine": "Moxie Wavy Routine",
        "products": [
            "gentle-cleansing-shampoo",
            "ultra-hydrating-conditioner",
            "weightless-leave-in-conditioner",
            "flexi-styling-serum-gel",
        ],
        "reason": "Wave definition + frizz control for wavy hair",
    },
    {
        "match": {"hair_pattern": "curly", "primary_goal": "curl_definition"},
        "routine": "Moxie Curly Routine",
        "products": [
            "gentle-cleansing-shampoo",
            "ultra-hydrating-conditioner",
            "super-defining-curl-cream",
            "flexi-styling-serum-gel",
        ],
        "reason": "Curl definition + hydration for curly hair",
    },
    {
        "match": {"hair_pattern": "wavy"},
        "routine": "Moxie Wavy Routine",
        "products": [
            "gentle-cleansing-shampoo",
            "ultra-hydrating-conditioner",
            "weightless-leave-in-conditioner",
            "flexi-styling-serum-gel",
        ],
        "reason": "Full wavy hair care routine",
    },
    {
        "match": {"hair_pattern": "curly"},
        "routine": "Moxie Curly Routine",
        "products": [
            "gentle-cleansing-shampoo",
            "ultra-hydrating-conditioner",
            "super-defining-curl-cream",
            "flexi-styling-serum-gel",
        ],
        "reason": "Full curly hair care routine",
    },
    {
        "match": {"primary_goal": "frizz_control"},
        "routine": "Ditch the Frizz Trio",
        "products": [
            "gentle-cleansing-shampoo",
            "ultra-hydrating-conditioner",
            "frizz-fighting-hair-serum",
        ],
        "reason": "Frizz control for all hair types",
    },
    {
        "match": {"primary_goal": "damage_repair"},
        "routine": "HydroRepair Routine",
        "products": [
            "hyaluronic-acid-repairing-shampoo",
            "hyaluronic-acid-repairing-conditioner",
            "hyaluronic-acid-repairing-serum",
        ],
        "reason": "Repair and rebuild damaged hair",
    },
    {
        "match": {"primary_goal": "general_care"},
        "routine": "Rinse & Shine Duo",
        "products": [
            "gentle-cleansing-shampoo",
            "ultra-hydrating-conditioner",
        ],
        "reason": "Essential daily hair care",
    },
]

FALLBACK_ROUTINE = {
    "routine": "Rinse & Shine Duo",
    "products": ["gentle-cleansing-shampoo", "ultra-hydrating-conditioner"],
    "reason": "A great starting point for healthy hair",
}


def recommend_routine(
    hair_pattern: str,
    primary_goal: str = "general_care",
    is_chemically_treated: bool = False,
    is_colored: bool = False,
) -> dict:
    inputs = {
        "hair_pattern": hair_pattern,
        "primary_goal": primary_goal,
        "is_chemically_treated": is_chemically_treated,
        "is_colored": is_colored,
    }
    for rule in RECOMMENDATION_RULES:
        if all(inputs.get(k) == v for k, v in rule["match"].items()):
            result = {
                "routine": rule["routine"],
                "reason": rule["reason"],
                "products": [],
            }
            for handle in rule["products"]:
                info = PRODUCT_CATALOG.get(handle, {})
                result["products"].append({
                    "handle": handle,
                    "name": info.get("name", handle),
                    "price": info.get("price", ""),
                    "url": info.get("url", ""),
                })
            return result
    result = {
        "routine": FALLBACK_ROUTINE["routine"],
        "reason": FALLBACK_ROUTINE["reason"],
        "products": [],
    }
    for handle in FALLBACK_ROUTINE["products"]:
        info = PRODUCT_CATALOG.get(handle, {})
        result["products"].append({
            "handle": handle,
            "name": info.get("name", handle),
            "price": info.get("price", ""),
            "url": info.get("url", ""),
        })
    return result


def get_product(product_handle: str) -> dict:
    info = PRODUCT_CATALOG.get(product_handle)
    if not info:
        return {"error": f"Product '{product_handle}' not found"}
    return {"handle": product_handle, **info}
