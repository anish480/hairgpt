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


SAMPLER_MAP = {
    "weightless-leave-in-conditioner": "weightless-leave-in-conditioner-sampler",
    "flexi-styling-serum-gel": "flexi-styling-serum-gel-sampler",
    "super-defining-curl-cream": "super-defining-curl-cream-sampler",
    "gentle-cleansing-shampoo": "gentle-cleansing-shampoo-sampler",
    "ultra-hydrating-conditioner": "ultra-hydrating-conditioner-sampler",
}

TRAVEL_MAP = {
    "weightless-leave-in-conditioner": "weightless-leave-in-conditioner-travel-size",
    "flexi-styling-serum-gel": "flexi-styling-serum-gel-travel-size",
    "super-defining-curl-cream": "super-defining-curl-cream-travel-size",
    "gentle-cleansing-shampoo": "gentle-cleansing-shampoo-travel-size",
    "ultra-hydrating-conditioner": "ultra-hydrating-conditioner-travel-size",
}

SAMPLER_SET_MAP = {
    "wavy": "moxie-wavy-sampler-set",
    "curly": "moxie-curly-sampler-set",
}

TRAVEL_ROUTINE_MAP = {
    "wavy": "the-moxie-wavy-travel-routine",
    "curly": "the-moxie-curly-travel-routine",
}


def _get_trial_option(handle: str) -> dict | None:
    result = {}

    travel_h = TRAVEL_MAP.get(handle)
    if travel_h and travel_h in PRODUCT_CATALOG:
        info = PRODUCT_CATALOG[travel_h]
        price = info.get("price", "")
        if price and price not in ("₹0", "Rs. 0.00", ""):
            result["travel"] = {
                "handle": travel_h,
                "name": info.get("name", travel_h),
                "price": price,
                "url": info.get("url", ""),
                "image": info.get("image_src", ""),
            }

    sampler_h = SAMPLER_MAP.get(handle)
    if sampler_h and sampler_h in PRODUCT_CATALOG:
        info = PRODUCT_CATALOG[sampler_h]
        result["sampler"] = {
            "handle": sampler_h,
            "name": info.get("name", sampler_h),
            "price": "Free",
        }

    return result if result else None


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
    user_experience: str = "novice",
    wants_wash: bool = True,
) -> dict:
    """Build a personalised step-by-step routine by composing product lines.

    Phase 1 (steps 1-2): Wash — chosen by hair CONCERN (scalp, dryness/frizz, damage).
    Phase 2 (steps 3-4): Style — optional, chosen by hair TEXTURE (curly, wavy, straight).
    """

    needs_repair = is_chemically_treated or is_colored
    is_straight = formation == "straight"
    is_wavy = formation == "wavy"
    is_curly = formation == "curly"

    steps: list[dict] = []
    routine_names: list[str] = []
    reasoning: list[str] = []

    concern_needs_hydration = primary_concern in (
        "dryness", "damage_repair",
    ) or needs_repair

    # --- Phase 1: Wash (from concern) ---
    if has_scalp_concern:
        routine_names.append("ScalpSOS")
        reasoning.append("Scalp concern detected — starting with the ScalpSOS wash to treat dandruff and irritation.")
        for handle, name, desc in WASH_SCALP:
            steps.append(_product_info(handle, desc))
    elif concern_needs_hydration:
        routine_names.append("HydroRepair")
        reasoning.append("Your hair needs deep hydration — the HydroRepair wash replenishes moisture and strengthens from within.")
        for handle, name, desc in WASH_HYDROREPAIR:
            steps.append(_product_info(handle, desc))
    else:
        routine_names.append("Rinse & Shine")
        reasoning.append("Starting with a gentle cleanse and deep conditioning — the foundation of any good routine.")
        for handle, name, desc in WASH_GENTLE:
            steps.append(_product_info(handle, desc))

    # --- Phase 2: Style / Treat (from texture, optional) ---
    if is_curly or (is_wavy and hair_type in ("2C",)):
        routine_names.append("Curly Vibe Setter")
        reasoning.append("Adding curl cream + serum gel to define and hold your natural curl pattern.")
        for handle, name, desc in STYLE_CURLY:
            steps.append(_product_info(handle, desc))
    elif is_wavy:
        routine_names.append("Wavy Vibe Setter")
        reasoning.append("Adding leave-in + serum gel to enhance and hold your wave pattern.")
        for handle, name, desc in STYLE_WAVY:
            steps.append(_product_info(handle, desc))
    elif is_straight and (has_frizz or primary_concern == "frizz_control"):
        routine_names.append("Ditch the Frizz")
        reasoning.append("Frizz Fighting Serum on damp hair — deeply hydrates without weighing your hair down.")
        for handle, name, desc in TREAT_FRIZZ:
            steps.append(_product_info(handle, desc))
    elif is_straight and concern_needs_hydration:
        routine_names.append("HydroRepair Boost")
        reasoning.append("Adding the HA serum to seal in repair benefits and protect against further damage.")
        for handle, name, desc in TREAT_HYDROREPAIR_SERUM:
            steps.append(_product_info(handle, desc))

    # --- Scalp add-on (if scalp concern + textured hair) ---
    if has_scalp_concern and not is_straight:
        reasoning.append("Optional add-on: a daily scalp serum to keep irritation in check between washes.")
        for handle, name, desc in TREAT_SCALP_SERUM:
            info = _product_info(handle, desc)
            info["optional"] = True
            steps.append(info)

    for i, step in enumerate(steps):
        step["step"] = i + 1

    routine_label = " + ".join(routine_names) if routine_names else "Custom Routine"

    # --- Determine cohort ---
    is_styling_concern = primary_concern in ("wave_definition", "curl_definition", "style")
    is_scalp_primary = has_scalp_concern and primary_concern == "scalp"

    if is_scalp_primary and is_styling_concern:
        cohort = "combined"
    elif is_scalp_primary:
        cohort = "concern"
    elif is_styling_concern:
        cohort = "styling"
    else:
        cohort = "general"

    # --- Phase tagging for novice users ---
    if user_experience == "novice":
        wash_handles = [h for h, _, _ in WASH_GENTLE + WASH_HYDROREPAIR + WASH_SCALP]
        style_handles = [h for h, _, _ in STYLE_WAVY + STYLE_CURLY + TREAT_FRIZZ]
        treat_handles = [h for h, _, _ in TREAT_FRIZZ + TREAT_HYDROREPAIR_SERUM + TREAT_SCALP_SERUM]

        for step in steps:
            step["phase"] = "foundation"

        if cohort == "styling":
            for step in steps:
                if step["handle"] in wash_handles:
                    if not wants_wash:
                        step["phase"] = "supporting"
                else:
                    step["phase"] = "foundation"
        elif cohort == "concern":
            for step in steps:
                if step.get("optional"):
                    step["phase"] = "enhancement"
        elif cohort == "combined":
            for step in steps:
                if step["handle"] in style_handles:
                    step["phase"] = "enhancement"
        else:
            for step in steps:
                if step["handle"] in treat_handles:
                    step["phase"] = "enhancement"

        for step in steps:
            if step.get("phase") == "enhancement":
                trial = _get_trial_option(step["handle"])
                if trial:
                    step["trial_option"] = trial
    else:
        for step in steps:
            step["phase"] = "full"
        cohort = "full"

    return {
        "routine": routine_label,
        "steps": steps,
        "reasoning": reasoning,
        "total_steps": len(steps),
        "user_experience": user_experience,
        "cohort": cohort,
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


def _check_compatibility(formation: str, steps: list[dict]) -> list[str]:
    warnings = []
    handles = [s["handle"] for s in steps]

    if "frizz-fighting-hair-serum" in handles and formation in ("curly",):
        warnings.append(
            "Frizz Fighting Serum isn't designed for curly routines — "
            "it can weigh down curl definition. Consider the styling duo instead."
        )
    if "frizz-fighting-hair-serum" in handles and formation == "wavy":
        warnings.append(
            "For wavier patterns (2B/2C), the Wavy Vibe Setter duo "
            "handles frizz AND definition. The serum is best for straighter textures."
        )

    ha_present = "hyaluronic-acid-hair-serum" in handles
    styling_present = any(
        h in handles for h in
        ["weightless-leave-in-conditioner", "super-defining-curl-cream", "flexi-styling-serum-gel"]
    )
    if ha_present and styling_present:
        warnings.append(
            "HA Serum can't be layered with leave-in or curl cream — "
            "it weighs down texture. Your HydroRepair wash already delivers repair."
        )

    return warnings


def adjust_routine(
    current_inputs: dict,
    adjustment_type: str,
    new_concern: str | None = None,
) -> dict:
    inputs = dict(current_inputs)

    if adjustment_type == "change_concern" and new_concern:
        inputs["primary_concern"] = new_concern
    elif adjustment_type == "add_scalp":
        inputs["has_scalp_concern"] = True
    elif adjustment_type == "drop_scalp":
        inputs["has_scalp_concern"] = False
    elif adjustment_type == "swap_to_gentle":
        inputs["primary_concern"] = "general_care"
        inputs["is_chemically_treated"] = False
        inputs["is_colored"] = False
    elif adjustment_type == "swap_to_hydrorepair":
        inputs["primary_concern"] = "damage_repair"
    elif adjustment_type == "swap_to_scalp":
        inputs["has_scalp_concern"] = True

    result = recommend_routine(**inputs)

    warnings = _check_compatibility(inputs.get("formation", "wavy"), result["steps"])
    if warnings:
        result["compatibility_warnings"] = warnings

    result["adjusted_from"] = current_inputs
    return result


def get_product(product_handle: str) -> dict:
    info = PRODUCT_CATALOG.get(product_handle)
    if not info:
        return {"error": f"Product '{product_handle}' not found"}
    return {"handle": product_handle, **info}
