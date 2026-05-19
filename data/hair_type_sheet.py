"""Ingest the "Hair type and product recommendations" Google Sheet into kb_chunks.

This sheet has ~92 rows mapping (hair_type, chemically_treated, coloured, frizz)
→ a Moxie routine + detailed comments. Many rows share identical comment blocks
with only the structured fields varying. We deduplicate by comment content and
merge the structured metadata across rows that share the same recommendation text.

Per unique routine-comment pair we generate up to 3 chunks:
  1. recommendation_rule  — the mapping: attributes → routine → product list
  2. product_education    — what each product does, why it works, who it's for
  3. cheat_sheet          — when to recommend / not recommend, troubleshooting tips

Run:
    uv run python -m app.ingest.hair_type_sheet --csv data/hair_type_recommendations.csv [--dry-run]
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Product handle normalisation
# ---------------------------------------------------------------------------

# Map messy product names from the sheet to canonical Shopify handles.
# Update these once you verify against the actual Storefront API product list.
PRODUCT_NAME_TO_HANDLE: dict[str, str] = {
    "gentle cleansing shampoo": "gentle-cleansing-shampoo",
    "ultra hydrating conditioner": "ultra-hydrating-conditioner",
    "ultra hydraitng conditioner": "ultra-hydrating-conditioner",  # typo in sheet
    "frizz fighting hair serum": "frizz-fighting-hair-serum",
    "weightless leave-in conditioner": "weightless-leave-in-conditioner",
    "weightless leave in conditioner": "weightless-leave-in-conditioner",
    "flexi styling serum gel": "flexi-styling-serum-gel",
    "flexi styling serum": "flexi-styling-serum-gel",
    "flexi srtyling hair serum": "flexi-styling-serum-gel",  # typo
    "super defining curl cream": "super-defining-curl-cream",
    "hyaluronic acid shampoo": "hyaluronic-acid-repairing-shampoo",
    "hyaluronic acid repairing shampoo": "hyaluronic-acid-repairing-shampoo",
    "hyaluronic acid conditioner": "hyaluronic-acid-repairing-conditioner",
    "hyaluronic acid repairing conditioner": "hyaluronic-acid-repairing-conditioner",
    "hyaluronic acd conditioner": "hyaluronic-acid-repairing-conditioner",  # typo
    "hyalurnoic acid conditioner": "hyaluronic-acid-repairing-conditioner",  # typo
    "hyaluronic acid serum": "hyaluronic-acid-repairing-serum",
    "hyaluronic acid hair serum": "hyaluronic-acid-repairing-serum",
    "leave in conditioner": "weightless-leave-in-conditioner",
    "curl cream": "super-defining-curl-cream",
    "curling cream": "super-defining-curl-cream",
    "serum gel": "flexi-styling-serum-gel",
}


def extract_product_handles(text: str) -> list[str]:
    """Extract canonical product handles from free-text product mentions."""
    text_lower = text.lower()
    found: list[str] = []
    # Sort by length descending so longer matches win over substrings
    for name, handle in sorted(PRODUCT_NAME_TO_HANDLE.items(), key=lambda x: -len(x[0])):
        if name in text_lower and handle not in found:
            found.append(handle)
    return found


# ---------------------------------------------------------------------------
# Topic tag inference
# ---------------------------------------------------------------------------

TAG_KEYWORDS: dict[str, list[str]] = {
    "frizz": ["frizz", "frizzy", "flyaway", "flyaways", "puffy"],
    "curls": ["curl", "curly", "curls", "coily", "coil", "curl definition", "curl pattern"],
    "waves": ["wave", "wavy", "waves", "wave definition", "wave pattern"],
    "dryness": ["dry", "dryness", "parched", "brittle", "moisture"],
    "damage": ["damage", "damaged", "breakage", "split end", "weakened"],
    "colour_treated": ["colour", "color", "coloured", "colored", "colour-treated", "color-treated"],
    "chemically_treated": ["chemical", "chemically", "straightening", "smoothening", "protein treatment", "keratin"],
    "heat_styling": ["heat styl", "heat damage", "flat iron", "blow dry"],
    "fine_hair": ["fine hair", "limp", "flat hair", "lightweight"],
    "oily_scalp": ["oily", "greasy", "sebum"],
    "dandruff": ["dandruff", "flake", "flaky", "flaky scalp"],
    "scalp_care": ["oily scalp", "scalp buildup", "scalp condition", "scalp issue"],
    "hold": ["hold", "definition", "lasting", "longer hold"],
    "hydration": ["hydrat", "moisture", "nourish"],
    "repair": ["repair", "restore", "rebuild", "strengthen"],
    "volume": ["volume", "bouncy", "bounce", "body"],
}


def infer_tags(text: str) -> list[str]:
    """Infer topic tags from text using keyword matching."""
    text_lower = text.lower()
    tags: list[str] = []
    for tag, keywords in TAG_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            tags.append(tag)
    return tags


# ---------------------------------------------------------------------------
# Hair type normalisation
# ---------------------------------------------------------------------------

def normalise_hair_type(raw: str) -> Optional[str]:
    """Normalise hair type strings like '2A ', '3c', '1B' → '2a', '3c', '1b'."""
    cleaned = raw.strip().lower()
    if re.match(r"^[1-4][a-c]$", cleaned):
        return cleaned
    return None


def hair_type_to_category(ht: str) -> Optional[str]:
    """Map hair type code to broad category: straight/wavy/curly/coily."""
    if not ht:
        return None
    prefix = ht[0]
    return {"1": "straight", "2": "wavy", "3": "curly", "4": "coily"}.get(prefix)


def normalise_bool(raw: str) -> Optional[bool]:
    """Parse yes/no/Yes/No/YES → bool."""
    cleaned = raw.strip().lower()
    if cleaned in ("yes", "y", "true", "1"):
        return True
    if cleaned in ("no", "n", "false", "0", ""):
        return False
    return None


# ---------------------------------------------------------------------------
# Chunk data model
# ---------------------------------------------------------------------------

@dataclass
class Chunk:
    content: str
    source_type: str = "hair_type_sheet"
    source_url: str = ""
    source_id: str = ""
    chunk_type: str = ""
    topic_tags: list[str] = field(default_factory=list)
    product_refs: list[str] = field(default_factory=list)
    hair_types: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Comment block parsing
# ---------------------------------------------------------------------------

def split_comment_sections(comment: str) -> dict[str, str]:
    """Split a comment block into logical sections.
    
    Returns a dict with keys like 'overview', 'product_details', 'cheat_sheet'.
    """
    sections: dict[str, str] = {}
    
    # Find cheat sheet section
    cheat_patterns = [
        r"(?:Cheat\s*sheet|Cheatsheet)\s*:?\s*\n",
        r"(?:Cheat\s*sheet|Cheatsheet)\s*:?\s*$",
    ]
    cheat_start = None
    for pattern in cheat_patterns:
        match = re.search(pattern, comment, re.IGNORECASE | re.MULTILINE)
        if match:
            cheat_start = match.start()
            sections["cheat_sheet"] = comment[match.end():].strip()
            break
    
    # Everything before cheat sheet is the main content
    main = comment[:cheat_start].strip() if cheat_start else comment.strip()
    
    # Try to split main into overview vs product details
    # Product details usually start with "Shampoo:" or "Phase 1:" or similar
    product_patterns = [
        r"\n(?:Shampoo|Phase\s+\d|Hyaluronic\s+Acid\s+Repairing\s+Shampoo)\s*:",
    ]
    prod_start = None
    for pattern in product_patterns:
        match = re.search(pattern, main, re.IGNORECASE)
        if match:
            prod_start = match.start()
            sections["product_details"] = main[prod_start:].strip()
            break
    
    overview = main[:prod_start].strip() if prod_start else main.strip()
    if overview:
        sections["overview"] = overview
    
    return sections


# ---------------------------------------------------------------------------
# Routine name extraction
# ---------------------------------------------------------------------------

ROUTINE_NAMES: dict[str, str] = {
    "ditch the frizz trio": "dtft",
    "dtft": "dtft",
    "hydrorepair routine": "hydrorepair",
    "hydrorepair trio": "hydrorepair",
    "hydrorepair essentials trio": "hydrorepair",
    "hydrorepair duo": "hydrorepair",
    "moxie wavvy routine": "wavy_full",
    "moxie wavy routine": "wavy_full",
    "moxie wvvy routine": "wavy_full",
    "moxie curly routine": "curly_full",
    "rinse and shine duo": "rinse_and_shine",
    "curly vibe setter duo": "curly_vibe_setter",
    "wavy vibe setter duo": "wavy_vibe_setter",
}


def extract_routine_id(recommendation: str) -> str:
    """Extract a normalised routine ID from the recommendation text."""
    rec_lower = recommendation.lower()
    for pattern, routine_id in ROUTINE_NAMES.items():
        if pattern in rec_lower:
            return routine_id
    
    # Check for path-based recommendations
    if "path a" in rec_lower and "path b" in rec_lower:
        if "wave definition" in rec_lower or "wavy" in rec_lower:
            return "wavy_paths_ab"
        if "curl" in rec_lower:
            return "curly_paths_ab"
        if "damage repair" in rec_lower or "hydrorepair" in rec_lower:
            return "repair_plus_styling"
    
    if "path a" in rec_lower:
        if "wave" in rec_lower:
            return "wavy_path_a"
        return "path_a_generic"
    
    return "unknown"


# ---------------------------------------------------------------------------
# Core ingestion logic
# ---------------------------------------------------------------------------

@dataclass
class RoutineGroup:
    """Groups rows that share the same recommendation + comment content."""
    routine_id: str
    recommendation_text: str
    comment_text: str
    hair_types: set[str] = field(default_factory=set)
    hair_categories: set[str] = field(default_factory=set)
    frizz_values: set[bool] = field(default_factory=set)
    chem_treated_values: set[bool] = field(default_factory=set)
    coloured_values: set[bool] = field(default_factory=set)
    row_indices: list[int] = field(default_factory=list)
    product_handles: list[str] = field(default_factory=list)


def group_rows(rows: list[dict]) -> list[RoutineGroup]:
    """Group rows by (recommendation_text, comment_first_120_chars) dedup key."""
    groups: dict[str, RoutineGroup] = {}
    
    for i, row in enumerate(rows):
        rec = row.get("Moxie's product recommendation", "").strip()
        comment = row.get("Comments", "").strip()
        if not rec and not comment:
            continue
        
        # Dedup key: hash of normalised recommendation + first 120 chars of comment
        rec_norm = re.sub(r"\s+", " ", rec.lower())
        comment_norm = re.sub(r"\s+", " ", comment[:120].lower())
        dedup_key = hashlib.md5(f"{rec_norm}|{comment_norm}".encode()).hexdigest()[:12]
        
        if dedup_key not in groups:
            routine_id = extract_routine_id(rec)
            product_handles = extract_product_handles(rec + "\n" + comment)
            groups[dedup_key] = RoutineGroup(
                routine_id=routine_id,
                recommendation_text=rec,
                comment_text=comment,
                product_handles=product_handles,
            )
        
        g = groups[dedup_key]
        g.row_indices.append(i)
        
        # Merge structured metadata
        ht_raw = row.get("Hair Type\n(2A, AB, 3C, etc)", "").strip()
        ht = normalise_hair_type(ht_raw)
        if ht:
            g.hair_types.add(ht)
            cat = hair_type_to_category(ht)
            if cat:
                g.hair_categories.add(cat)
        
        frizz = normalise_bool(row.get("Hair Frizz Present?\n(Yes / No)", ""))
        if frizz is not None:
            g.frizz_values.add(frizz)
        
        ct = normalise_bool(row.get("Is hair currently chemically treated?", ""))
        if ct is not None:
            g.chem_treated_values.add(ct)
        
        co = normalise_bool(row.get("Is hair coloured?", ""))
        if co is not None:
            g.coloured_values.add(co)
    
    return list(groups.values())


def generate_chunks(group: RoutineGroup, sheet_url: str) -> list[Chunk]:
    """Generate 1-3 KB chunks from a deduplicated routine group."""
    chunks: list[Chunk] = []
    
    hair_types_list = sorted(group.hair_types)
    hair_categories_list = sorted(group.hair_categories)
    all_tags = infer_tags(group.recommendation_text + "\n" + group.comment_text)
    
    # Add hair category tags
    for cat in hair_categories_list:
        tag = f"{cat}_hair"
        if tag not in all_tags:
            all_tags.append(tag)
    
    base_metadata = {
        "routine_id": group.routine_id,
        "row_count": len(group.row_indices),
        "hair_categories": hair_categories_list,
        "frizz_present": sorted(group.frizz_values) if group.frizz_values else None,
        "chemically_treated": sorted(group.chem_treated_values) if group.chem_treated_values else None,
        "coloured": sorted(group.coloured_values) if group.coloured_values else None,
    }
    
    source_id = f"hair_type_sheet_{group.routine_id}_{len(group.row_indices)}rows"
    
    sections = split_comment_sections(group.comment_text)
    
    # --- Chunk 1: Recommendation Rule ---
    # Combines the structured recommendation with the overview
    rule_parts = []
    rule_parts.append(f"Recommended routine: {group.recommendation_text.strip()}")
    rule_parts.append(f"Suitable hair types: {', '.join(hair_types_list) if hair_types_list else 'see details'}")
    if hair_categories_list:
        rule_parts.append(f"Hair categories: {', '.join(hair_categories_list)}")
    if True in group.chem_treated_values:
        rule_parts.append("Suitable for chemically treated hair: Yes")
    elif group.chem_treated_values == {False}:
        rule_parts.append("Suitable for chemically treated hair: No (virgin/untreated hair)")
    if True in group.coloured_values:
        rule_parts.append("Suitable for coloured hair: Yes")
    if True in group.frizz_values:
        rule_parts.append("Addresses frizz: Yes")
    
    if sections.get("overview"):
        rule_parts.append(f"\n{sections['overview']}")
    
    chunks.append(Chunk(
        content="\n".join(rule_parts),
        chunk_type="recommendation_rule",
        source_url=sheet_url,
        source_id=source_id,
        topic_tags=all_tags,
        product_refs=group.product_handles,
        hair_types=hair_types_list,
        metadata={**base_metadata, "chunk_type": "recommendation_rule"},
    ))
    
    # --- Chunk 2: Product Education (if present) ---
    if sections.get("product_details"):
        edu_content = f"Product details for {group.routine_id.replace('_', ' ').title()} routine:\n\n{sections['product_details']}"
        chunks.append(Chunk(
            content=edu_content,
            chunk_type="product_education",
            source_url=sheet_url,
            source_id=source_id,
            topic_tags=all_tags,
            product_refs=group.product_handles,
            hair_types=hair_types_list,
            metadata={**base_metadata, "chunk_type": "product_education"},
        ))
    
    # --- Chunk 3: Cheat Sheet / When-to-recommend guidance ---
    if sections.get("cheat_sheet"):
        cheat_content = f"When to recommend the {group.routine_id.replace('_', ' ').title()} routine:\n\n{sections['cheat_sheet']}"
        chunks.append(Chunk(
            content=cheat_content,
            chunk_type="cheat_sheet",
            source_url=sheet_url,
            source_id=source_id,
            topic_tags=all_tags,
            product_refs=group.product_handles,
            hair_types=hair_types_list,
            metadata={**base_metadata, "chunk_type": "cheat_sheet"},
        ))
    
    return chunks


def ingest_hair_type_csv(
    csv_path: str,
    sheet_url: str = "https://docs.google.com/spreadsheets/d/1CaaPjJfaLwKjkptwazPTm57xwaBsox-y4ABOJgIfpnA/edit",
) -> list[Chunk]:
    """Parse the CSV export and return deduplicated KB chunks."""
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    
    print(f"[hair_type_sheet] parsed {len(rows)} rows from {csv_path}")
    
    groups = group_rows(rows)
    print(f"[hair_type_sheet] deduplicated into {len(groups)} unique routine groups")
    
    all_chunks: list[Chunk] = []
    for g in groups:
        chunks = generate_chunks(g, sheet_url)
        all_chunks.extend(chunks)
        print(
            f"  {g.routine_id:<25s} | {len(g.row_indices):2d} rows | "
            f"hair_types={sorted(g.hair_types)} | "
            f"{len(chunks)} chunks"
        )
    
    print(f"[hair_type_sheet] total chunks: {len(all_chunks)}")
    return all_chunks


# ---------------------------------------------------------------------------
# DB write helpers (for use when Cloud SQL is available)
# ---------------------------------------------------------------------------

async def write_chunks_to_db(chunks: list[Chunk], pool) -> int:
    """Write chunks to the kb_chunks table. Returns count of rows inserted.
    
    Uses an upsert strategy: deactivates existing chunks from the same source,
    then inserts new ones. This makes re-ingestion idempotent.
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Deactivate old chunks from this source
            deactivated = await conn.execute(
                "UPDATE kb_chunks SET is_active = FALSE WHERE source_type = 'hair_type_sheet'"
            )
            print(f"[hair_type_sheet] deactivated old chunks: {deactivated}")
            
            # Insert new chunks
            inserted = 0
            for chunk in chunks:
                await conn.execute("""
                    INSERT INTO kb_chunks (
                        content, source_type, source_url, source_id,
                        chunk_type, topic_tags, product_refs, hair_types,
                        metadata, is_active, version
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, TRUE, 1)
                """,
                    chunk.content,
                    chunk.source_type,
                    chunk.source_url,
                    chunk.source_id,
                    chunk.chunk_type,
                    chunk.topic_tags,
                    chunk.product_refs,
                    chunk.hair_types,
                    __import__("json").dumps(chunk.metadata),
                )
                inserted += 1
            
            print(f"[hair_type_sheet] inserted {inserted} chunks")
            return inserted


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Ingest hair type recommendation sheet")
    parser.add_argument("--csv", required=True, help="Path to CSV export of the sheet")
    parser.add_argument("--dry-run", action="store_true", help="Parse and print chunks without writing to DB")
    parser.add_argument("--output-json", help="Write chunks to a JSON file (for inspection)")
    args = parser.parse_args()
    
    chunks = ingest_hair_type_csv(args.csv)
    
    if args.output_json:
        import json
        out = []
        for c in chunks:
            out.append({
                "content": c.content,
                "source_type": c.source_type,
                "source_url": c.source_url,
                "source_id": c.source_id,
                "chunk_type": c.chunk_type,
                "topic_tags": c.topic_tags,
                "product_refs": c.product_refs,
                "hair_types": c.hair_types,
                "metadata": c.metadata,
            })
        Path(args.output_json).write_text(json.dumps(out, indent=2))
        print(f"[hair_type_sheet] wrote {len(out)} chunks to {args.output_json}")
    
    if args.dry_run:
        print("\n" + "=" * 80)
        print("DRY RUN — sample chunks:")
        print("=" * 80)
        for i, c in enumerate(chunks[:6]):
            print(f"\n--- Chunk {i+1} [{c.chunk_type}] ---")
            print(f"Source ID: {c.source_id}")
            print(f"Products: {c.product_refs}")
            print(f"Hair types: {c.hair_types}")
            print(f"Tags: {c.topic_tags}")
            print(f"Content ({len(c.content)} chars):")
            print(c.content[:300] + ("..." if len(c.content) > 300 else ""))
        return
    
    # If not dry-run, write to DB
    import asyncio
    
    async def _write():
        # Import here to avoid requiring DB deps for dry-run
        from app.db import get_pool, close
        pool = await get_pool()
        try:
            count = await write_chunks_to_db(chunks, pool)
            print(f"[hair_type_sheet] done — {count} chunks written to DB")
        finally:
            await close()
    
    asyncio.run(_write())


if __name__ == "__main__":
    main()
