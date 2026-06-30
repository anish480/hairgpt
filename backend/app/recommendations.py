import json
from pathlib import Path

_LOCAL_CATALOG = Path(__file__).resolve().parents[2] / "data" / "product_catalog.json"
_DOCKER_CATALOG = Path("/data/product_catalog.json")
_CATALOG_PATH = _LOCAL_CATALOG if _LOCAL_CATALOG.exists() else _DOCKER_CATALOG


def _load_catalog() -> dict[str, dict]:
    if _CATALOG_PATH.exists():
        with open(_CATALOG_PATH) as f:
            return json.load(f)
    return {}


PRODUCT_CATALOG = _load_catalog()

# ---------------------------------------------------------------------------
# Product lines — the building blocks of a personalised routine
# ---------------------------------------------------------------------------

WASH_GENTLE = [
    ("gentle-cleansing-shampoo", "Gentle Cleansing Shampoo", "Gently cleanses buildup and impurities without stripping your hair."),
    ("ultra-hydrating-conditioner", "Ultra Hydrating Conditioner", "Deeply conditions and softens with shea butter — rich hydration during the wash."),
]

WASH_HYDROREPAIR = [
    ("hyaluronic-acid-repairing-shampoo", "Hyaluronic Acid Repairing Shampoo", "Replenishes lost moisture and reinforces your hair's natural barrier while cleansing."),
    ("hyaluronic-acid-repairing-conditioner", "Hyaluronic Acid Repairing Conditioner", "Protein-enriched formula that restores moisture balance and strengthens weakened strands."),
]

WASH_SCALP = [
    ("dandruff-detox-pre-wash-treatment", "Dandruff Detox Pre-Wash Treatment", "Exfoliates flakes and buildup from the scalp before washing."),
    ("scalp-reviving-shampoo", "Scalp Reviving Shampoo", "Sulphate-free formula that treats dandruff at the root with Piroctone Olamine."),
    ("moisture-restoring-conditioner", "Moisture Restoring Conditioner", "Hydrates and softens dry, stressed strands without heaviness."),
]

STYLE_WAVY = [
    ("weightless-leave-in-conditioner", "Weightless Leave-In Conditioner", "Primes your wave pattern with lightweight hydration and frizz reduction."),
    ("flexi-styling-serum-gel", "Flexi Styling Serum Gel", "Locks your waves in place with flexible hold — no crunch."),
]

STYLE_CURLY = [
    ("super-defining-curl-cream", "Super Defining Curl Cream", "Defines your curl pattern with moisture and softness."),
    ("flexi-styling-serum-gel", "Flexi Styling Serum Gel", "Holds curls together for longer-lasting definition and frizz control."),
]

TREAT_FRIZZ = [
    ("frizz-fighting-hair-serum", "Frizz Fighting Hair Serum (SPF 35)", "Apply on damp hair only — deeply hydrates the hair shaft to tackle frizz at its root cause. Not for use in wavy or curly routines."),
]

TREAT_HYDROREPAIR_SERUM = [
    ("hyaluronic-acid-hair-serum", "Hyaluronic Acid Hair Serum", "Deeply reparative leave-in that hydrates, smooths, and protects against heat and environmental stressors."),
]

TREAT_SCALP_SERUM = [
    ("daily-calming-leave-on-serum", "Daily Calming Leave-On Serum", "Lightweight scalp serum that soothes, strengthens, and protects — anytime, anywhere."),
]


_EXCLUDED_SUFFIXES = ("-sampler", "-15ml", "-10ml")
_COMBO_KEYWORDS = ("duo", "trio", "routine", "combo", "rinse-refill", "copy", "pouch", "set")


def _find_size_variants(base_handle: str) -> list[dict]:
    """Find all purchasable size variants for a product, excluding samplers and combos."""
    variants = []
    for h, info in PRODUCT_CATALOG.items():
        if not h.startswith(base_handle):
            continue
        if h == base_handle:
            continue
        if any(h.endswith(s) for s in _EXCLUDED_SUFFIXES):
            continue
        if any(kw in h for kw in _COMBO_KEYWORDS):
            continue
        price = info.get("price", "")
        if price in ("₹0", "Rs. 0.00", ""):
            continue
        variants.append({
            "handle": h,
            "name": info.get("name", h),
            "price": price,
            "url": info.get("url", ""),
        })
    return variants


def _product_info(handle: str, role_desc: str) -> dict:
    info = PRODUCT_CATALOG.get(handle, {})
    result = {
        "handle": handle,
        "name": info.get("name", handle),
        "price": info.get("price", ""),
        "url": info.get("url", ""),
        "image": info.get("image_src", ""),
        "why": role_desc,
        "sizes": [],
    }
    variants = _find_size_variants(handle)
    for v in variants:
        result["sizes"].append(v)
    return result


# ---------------------------------------------------------------------------
# Composable routine builder
# ---------------------------------------------------------------------------

def recommend_routine(
    hair_type: str = "2A",
    formation: str = "wavy",
    texture: str = "medium",
    primary_concern: str = "general_care",
    has_frizz: bool = False,
    is_chemically_treated: bool = False,
    is_colored: bool = False,
    has_scalp_concern: bool = False,
) -> dict:
    """Build a personalised step-by-step routine by composing product lines."""

    needs_repair = is_chemically_treated or is_colored
    is_straight = formation == "straight"
    is_wavy = formation == "wavy"
    is_curly = formation == "curly"
    is_fine = texture == "fine"

    steps: list[dict] = []
    routine_names: list[str] = []
    reasoning: list[str] = []

    # --- Phase 1: Wash ---
    if has_scalp_concern:
        routine_names.append("ScalpSOS")
        reasoning.append("Scalp concern detected — starting with the ScalpSOS wash to treat dandruff and irritation.")
        for handle, name, desc in WASH_SCALP:
            steps.append(_product_info(handle, desc))
    elif needs_repair or primary_concern == "damage_repair":
        routine_names.append("HydroRepair")
        reasoning.append("Your hair needs repair — the HydroRepair wash will rebuild moisture and strength.")
        for handle, name, desc in WASH_HYDROREPAIR:
            steps.append(_product_info(handle, desc))
    else:
        routine_names.append("Rinse & Shine")
        reasoning.append("Starting with a gentle cleanse and deep conditioning — the foundation of any good routine.")
        for handle, name, desc in WASH_GENTLE:
            steps.append(_product_info(handle, desc))

    # --- Phase 2: Style / Treat ---
    wants_definition = primary_concern in ("wave_definition", "curl_definition", "style")

    if is_curly or (is_wavy and hair_type in ("2C",) and wants_definition):
        routine_names.append("Curly Vibe Setter")
        reasoning.append("Adding curl cream + serum gel to define and hold your natural curl pattern.")
        for handle, name, desc in STYLE_CURLY:
            steps.append(_product_info(handle, desc))
    elif is_wavy and wants_definition:
        routine_names.append("Wavy Vibe Setter")
        reasoning.append("Adding leave-in + serum gel to enhance and hold your wave pattern.")
        for handle, name, desc in STYLE_WAVY:
            steps.append(_product_info(handle, desc))
    elif is_wavy and (has_frizz or primary_concern == "frizz_control"):
        routine_names.append("Wavy Vibe Setter")
        reasoning.append("Leave-in + serum gel combo — handles frizz while enhancing your waves. The Frizz Fighting Serum isn't suitable for wavy hair routines.")
        for handle, name, desc in STYLE_WAVY:
            steps.append(_product_info(handle, desc))
    elif is_straight and (has_frizz or primary_concern == "frizz_control"):
        routine_names.append("Ditch the Frizz")
        reasoning.append("Frizz Fighting Serum on damp hair — deeply hydrates without weighing your hair down.")
        for handle, name, desc in TREAT_FRIZZ:
            steps.append(_product_info(handle, desc))
    elif primary_concern == "damage_repair":
        routine_names.append("HydroRepair Boost")
        reasoning.append("Your hair needs repair — adding the HA serum to deeply hydrate and protect against further damage.")
        for handle, name, desc in TREAT_HYDROREPAIR_SERUM:
            steps.append(_product_info(handle, desc))
    elif needs_repair and not has_scalp_concern:
        if not any("Vibe Setter" in n for n in routine_names):
            reasoning.append("Adding the HA serum to seal in repair benefits and protect against further damage.")
            for handle, name, desc in TREAT_HYDROREPAIR_SERUM:
                steps.append(_product_info(handle, desc))

    # --- Phase 3: Scalp add-on (if scalp concern + other needs) ---
    if has_scalp_concern and not is_straight:
        reasoning.append("Adding a daily scalp serum to keep irritation in check between washes.")
        for handle, name, desc in TREAT_SCALP_SERUM:
            steps.append(_product_info(handle, desc))

    # --- Fallback: if only wash and no treat/style was added ---
    if len(steps) <= 2 and not has_scalp_concern:
        if has_frizz and is_straight:
            routine_names.append("Ditch the Frizz")
            reasoning.append("Adding frizz serum on damp hair for that extra smoothness.")
            for handle, name, desc in TREAT_FRIZZ:
                steps.append(_product_info(handle, desc))

    # Number the steps
    for i, step in enumerate(steps):
        step["step"] = i + 1

    routine_label = " + ".join(routine_names) if routine_names else "Custom Routine"

    return {
        "routine": routine_label,
        "steps": steps,
        "reasoning": reasoning,
        "total_steps": len(steps),
        "inputs": {
            "hair_type": hair_type,
            "formation": formation,
            "texture": texture,
            "primary_concern": primary_concern,
            "has_frizz": has_frizz,
            "is_chemically_treated": is_chemically_treated,
            "is_colored": is_colored,
            "has_scalp_concern": has_scalp_concern,
        },
    }


def get_product(product_handle: str) -> dict:
    info = PRODUCT_CATALOG.get(product_handle)
    if not info:
        return {"error": f"Product '{product_handle}' not found"}
    return {"handle": product_handle, **info}
