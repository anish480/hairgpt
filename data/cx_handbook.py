"""Ingest the Moxie CX Handbook PDF into kb_chunks.

The handbook is a structured 27-page document with 10 numbered sections.
Unlike the hair type sheet (tabular, heavy dedup), this is prose with clear
section boundaries. We split on section/subsection headers and generate
one chunk per logical knowledge unit.

Chunk types produced:
  - product_catalogue     : per-product details (ingredients, benefits, usage)
  - routine_steps         : step-by-step routine instructions
  - clinical_data         : clinical test results and study references
  - product_comparison    : "which X?" differentiation tables
  - troubleshooting       : problem → solution pairs
  - hair_type_guide       : hair type → routine mapping
  - ingredient_info       : ingredient details, protein content, fragrance, SPF
  - special_case          : edge cases (pregnancy, kids, protein-sensitive, etc.)
  - policy                : orders, delivery, returns, refunds
  - escalation_rule       : when to flag to Rupika
  - tone_guide            : voice guidelines and response templates
  - quick_reference       : cheat sheet, decision tree, offers, contacts

Run:
    uv run python -m app.ingest.cx_handbook --pdf data/Moxie_Cx_Handbook_290426.pdf [--dry-run]

Or with pre-extracted text:
    uv run python -m app.ingest.cx_handbook --text data/cx_handbook.txt [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Re-use shared helpers from the hair type sheet ingester
from app.ingest.hair_type_sheet import (
    Chunk,
    extract_product_handles,
    infer_tags,
)

# ---------------------------------------------------------------------------
# Section definitions — maps section headers to chunk_type + metadata
# ---------------------------------------------------------------------------

SECTION_CONFIG: list[dict] = [
    {
        "pattern": r"Section 1[:\s]",
        "title": "Complete Product Catalogue",
        "chunk_type": "product_catalogue",
    },
    {
        "pattern": r"Section 2[:\s]",
        "title": "Product Differentiation Guide",
        "chunk_type": "product_comparison",
    },
    {
        "pattern": r"Section 3[:\s]",
        "title": "Hair Type Reference and Recommendations",
        "chunk_type": "hair_type_guide",
    },
    {
        "pattern": r"Section 4[:\s]",
        "title": "Key Ingredients and FAQs",
        "chunk_type": "ingredient_info",
    },
    {
        "pattern": r"Section 5[:\s]",
        "title": "Troubleshooting Guide",
        "chunk_type": "troubleshooting",
    },
    {
        "pattern": r"Section 6[:\s]",
        "title": "Special Use Cases and Edge Cases",
        "chunk_type": "special_case",
    },
    {
        "pattern": r"Section 7[:\s]",
        "title": "Orders, Delivery, and Returns",
        "chunk_type": "policy",
    },
    {
        "pattern": r"Section 8[:\s]",
        "title": "When to Flag to Rupika",
        "chunk_type": "escalation_rule",
    },
    {
        "pattern": r"Section 9[:\s]",
        "title": "Tone and Response Templates",
        "chunk_type": "tone_guide",
    },
    {
        "pattern": r"Section 10[:\s]",
        "title": "Quick Reference Cheat Sheet",
        "chunk_type": "quick_reference",
    },
]

# Sub-section patterns within Section 1 (product ranges)
PRODUCT_RANGE_PATTERNS: list[dict] = [
    {"pattern": r"1A\.\s*Wave Enhancing Range", "range_id": "wave_enhancing", "hair_types": ["2a", "2b", "2c"]},
    {"pattern": r"1B\.\s*Curl Defining Range", "range_id": "curl_defining", "hair_types": ["3a", "3b", "3c"]},
    {"pattern": r"1C\.\s*Frizz Fighting Range", "range_id": "frizz_fighting", "hair_types": []},
    {"pattern": r"1D\.\s*Scalp Reviving", "range_id": "scalp_reviving", "hair_types": []},
    {"pattern": r"1E\.\s*HydroRepair Range", "range_id": "hydrorepair", "hair_types": []},
    {"pattern": r"1F\.\s*Style Sculpting Range", "range_id": "style_sculpting", "hair_types": []},
    {"pattern": r"1G\.\s*Gentle Cleansing Shampoo.*Core Duo", "range_id": "core_duo", "hair_types": []},
]

# Sub-section patterns within Section 2 (product comparisons)
COMPARISON_PATTERNS: list[dict] = [
    {"pattern": r"2A\.\s*Which Shampoo", "comparison_id": "shampoo_comparison"},
    {"pattern": r"2B\.\s*Which Conditioner", "comparison_id": "conditioner_comparison"},
    {"pattern": r"2C\.\s*Which Styler", "comparison_id": "styler_comparison"},
]

# Troubleshooting sub-sections within Section 5
TROUBLESHOOT_PATTERNS: list[str] = [
    r"Wavy or Curly Routine Not Working",
    r"Hair Feels Rough or Stiff",
    r"More Frizzy After Routine",
    r"Shampoo Causing Dryness",
    r"Products Causing Hairfall",
    r"Products Causing Acne",
    r"Firefighter.*Feeling Greasy",
    r"HydroRepair.*Not Working",
    r"Deep Dive Mask.*Not Work",
    r"Shampoo Solidifying",
    r"Products Pilling or Curdling",
]


# ---------------------------------------------------------------------------
# Text splitting utilities
# ---------------------------------------------------------------------------

def split_on_sections(text: str) -> list[tuple[str, str, str]]:
    """Split full text into (section_title, chunk_type, section_text) tuples.
    
    Also splits the preamble (before Section 1) as a 'golden_rules' chunk.
    """
    results: list[tuple[str, str, str]] = []
    
    # Find all section boundaries
    boundaries: list[tuple[int, str, str]] = []
    for cfg in SECTION_CONFIG:
        match = re.search(cfg["pattern"], text, re.IGNORECASE)
        if match:
            boundaries.append((match.start(), cfg["title"], cfg["chunk_type"]))
    
    boundaries.sort(key=lambda x: x[0])
    
    # Extract preamble (golden rules, how to use)
    if boundaries:
        preamble = text[:boundaries[0][0]].strip()
        if preamble and len(preamble) > 50:
            results.append(("Golden Rules and Guidelines", "tone_guide", preamble))
    
    # Extract each section
    for i, (start, title, chunk_type) in enumerate(boundaries):
        end = boundaries[i + 1][0] if i + 1 < len(boundaries) else len(text)
        section_text = text[start:end].strip()
        results.append((title, chunk_type, section_text))
    
    return results


def split_product_ranges(section_text: str) -> list[tuple[str, str, list[str], str]]:
    """Split Section 1 into individual product range sub-sections.
    
    Returns list of (range_id, range_title_line, hair_types, range_text).
    """
    results: list[tuple[str, str, list[str], str]] = []
    
    boundaries: list[tuple[int, str, list[str]]] = []
    for cfg in PRODUCT_RANGE_PATTERNS:
        match = re.search(cfg["pattern"], section_text, re.IGNORECASE)
        if match:
            boundaries.append((match.start(), cfg["range_id"], cfg["hair_types"]))
    
    boundaries.sort(key=lambda x: x[0])
    
    for i, (start, range_id, hair_types) in enumerate(boundaries):
        end = boundaries[i + 1][0] if i + 1 < len(boundaries) else len(section_text)
        range_text = section_text[start:end].strip()
        results.append((range_id, range_id.replace("_", " ").title(), hair_types, range_text))
    
    return results


def split_comparisons(section_text: str) -> list[tuple[str, str]]:
    """Split Section 2 into individual comparison sub-sections."""
    results: list[tuple[str, str]] = []
    
    boundaries: list[tuple[int, str]] = []
    for cfg in COMPARISON_PATTERNS:
        match = re.search(cfg["pattern"], section_text, re.IGNORECASE)
        if match:
            boundaries.append((match.start(), cfg["comparison_id"]))
    
    boundaries.sort(key=lambda x: x[0])
    
    for i, (start, comp_id) in enumerate(boundaries):
        end = boundaries[i + 1][0] if i + 1 < len(boundaries) else len(section_text)
        comp_text = section_text[start:end].strip()
        results.append((comp_id, comp_text))
    
    return results


def split_clinical_from_product(text: str) -> tuple[str, Optional[str]]:
    """Separate clinical data from product description text.
    
    Returns (product_text, clinical_text_or_none).
    """
    clinical_pattern = r"CLINICALLY TESTED.*?(?=\n\n[A-Z1-9]|\Z)"
    match = re.search(clinical_pattern, text, re.DOTALL)
    if match:
        clinical = match.group(0).strip()
        product = text[:match.start()].strip()
        # There might be more product text after clinical
        remaining = text[match.end():].strip()
        if remaining:
            product += "\n\n" + remaining
        return product, clinical
    return text, None


def extract_routine_steps(text: str) -> Optional[str]:
    """Extract step-by-step routine instructions if present."""
    # Look for "Step by Step" or "Step Product How to Apply" patterns
    patterns = [
        r"(?:Step by Step|Step\s+Product\s+How to Apply)(.*?)(?=CLINICALLY|$)",
        r"(Step 1:.*?Step 4:.*?)(?=CLINICALLY|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(0).strip()
    return None


def split_troubleshooting_pairs(section_text: str) -> list[tuple[str, str]]:
    """Split Section 5 into individual problem → solution pairs."""
    # Split on bold/header-like lines that describe the problem
    results: list[tuple[str, str]] = []
    
    # Split on known troubleshooting headers
    all_boundaries: list[tuple[int, str]] = []
    for pattern in TROUBLESHOOT_PATTERNS:
        match = re.search(pattern, section_text, re.IGNORECASE)
        if match:
            all_boundaries.append((match.start(), match.group(0)))
    
    all_boundaries.sort(key=lambda x: x[0])
    
    for i, (start, title) in enumerate(all_boundaries):
        end = all_boundaries[i + 1][0] if i + 1 < len(all_boundaries) else len(section_text)
        pair_text = section_text[start:end].strip()
        results.append((title.strip(), pair_text))
    
    return results


# ---------------------------------------------------------------------------
# Chunk size management
# ---------------------------------------------------------------------------

MAX_CHUNK_CHARS = 2000  # Target max; some chunks may exceed slightly


def maybe_split_large_chunk(content: str, chunk_type: str, base_id: str, **kwargs) -> list[dict]:
    """If content exceeds MAX_CHUNK_CHARS, split on paragraph boundaries."""
    if len(content) <= MAX_CHUNK_CHARS:
        return [{"content": content, "chunk_type": chunk_type, "source_id": base_id, **kwargs}]
    
    # Split on double newlines (paragraph breaks)
    paragraphs = re.split(r"\n\n+", content)
    parts: list[dict] = []
    current = ""
    part_num = 1
    
    for para in paragraphs:
        if len(current) + len(para) + 2 > MAX_CHUNK_CHARS and current:
            parts.append({
                "content": current.strip(),
                "chunk_type": chunk_type,
                "source_id": f"{base_id}_part{part_num}",
                **kwargs,
            })
            current = para
            part_num += 1
        else:
            current = current + "\n\n" + para if current else para
    
    if current.strip():
        parts.append({
            "content": current.strip(),
            "chunk_type": chunk_type,
            "source_id": f"{base_id}_part{part_num}" if part_num > 1 else base_id,
            **kwargs,
        })
    
    return parts


# ---------------------------------------------------------------------------
# Core ingestion
# ---------------------------------------------------------------------------

def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract text from PDF using pypdf."""
    from pypdf import PdfReader
    reader = PdfReader(pdf_path)
    pages = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages.append(text)
    return "\n\n".join(pages)


def ingest_cx_handbook(
    text: str,
    source_url: str = "internal://cx-handbook-april-2026",
) -> list[Chunk]:
    """Parse the CX handbook text and return KB chunks."""
    
    sections = split_on_sections(text)
    print(f"[cx_handbook] split into {len(sections)} top-level sections")
    
    all_chunks: list[Chunk] = []
    
    for section_title, chunk_type, section_text in sections:
        print(f"  Processing: {section_title} ({chunk_type}) — {len(section_text)} chars")
        
        if chunk_type == "product_catalogue":
            # Split into product ranges, then further split clinical data
            ranges = split_product_ranges(section_text)
            for range_id, range_title, hair_types, range_text in ranges:
                product_handles = extract_product_handles(range_text)
                tags = infer_tags(range_text)
                
                # Separate clinical data
                product_text, clinical_text = split_clinical_from_product(range_text)
                
                # Extract routine steps if present
                routine_text = extract_routine_steps(product_text)
                
                # Main product chunk
                for part in maybe_split_large_chunk(
                    product_text, "product_catalogue",
                    f"cx_handbook_product_{range_id}",
                ):
                    all_chunks.append(Chunk(
                        content=part["content"],
                        chunk_type=part["chunk_type"],
                        source_url=source_url,
                        source_id=part["source_id"],
                        topic_tags=tags,
                        product_refs=product_handles,
                        hair_types=hair_types,
                        metadata={"section": "product_catalogue", "range": range_id},
                    ))
                
                # Routine steps as a separate chunk (high retrieval value for "how to" queries)
                if routine_text and len(routine_text) > 100:
                    all_chunks.append(Chunk(
                        content=f"Step-by-step {range_title} routine:\n\n{routine_text}",
                        chunk_type="routine_steps",
                        source_url=source_url,
                        source_id=f"cx_handbook_routine_{range_id}",
                        topic_tags=tags,
                        product_refs=product_handles,
                        hair_types=hair_types,
                        metadata={"section": "routine_steps", "range": range_id},
                    ))
                
                # Clinical data as a separate chunk
                if clinical_text:
                    all_chunks.append(Chunk(
                        content=clinical_text,
                        chunk_type="clinical_data",
                        source_url=source_url,
                        source_id=f"cx_handbook_clinical_{range_id}",
                        topic_tags=tags + ["clinical_proof"],
                        product_refs=product_handles,
                        hair_types=hair_types,
                        metadata={"section": "clinical_data", "range": range_id},
                    ))
        
        elif chunk_type == "product_comparison":
            # Split into comparison sub-sections
            comparisons = split_comparisons(section_text)
            for comp_id, comp_text in comparisons:
                product_handles = extract_product_handles(comp_text)
                tags = infer_tags(comp_text)
                
                # Separate troubleshooting from comparison table
                troubleshoot_match = re.search(
                    r"(?:Shampoo|Conditioner|Styler)\s+Troubleshooting",
                    comp_text, re.IGNORECASE
                )
                if troubleshoot_match:
                    comparison_part = comp_text[:troubleshoot_match.start()].strip()
                    troubleshoot_part = comp_text[troubleshoot_match.start():].strip()
                    
                    for part in maybe_split_large_chunk(
                        comparison_part, "product_comparison",
                        f"cx_handbook_compare_{comp_id}",
                    ):
                        all_chunks.append(Chunk(
                            content=part["content"],
                            chunk_type=part["chunk_type"],
                            source_url=source_url,
                            source_id=part["source_id"],
                            topic_tags=tags,
                            product_refs=product_handles,
                            hair_types=[],
                            metadata={"section": "product_comparison", "comparison": comp_id},
                        ))
                    
                    for part in maybe_split_large_chunk(
                        troubleshoot_part, "troubleshooting",
                        f"cx_handbook_troubleshoot_{comp_id}",
                    ):
                        all_chunks.append(Chunk(
                            content=part["content"],
                            chunk_type="troubleshooting",
                            source_url=source_url,
                            source_id=part["source_id"],
                            topic_tags=tags + ["troubleshooting"],
                            product_refs=product_handles,
                            hair_types=[],
                            metadata={"section": "troubleshooting", "comparison": comp_id},
                        ))
                else:
                    for part in maybe_split_large_chunk(
                        comp_text, "product_comparison",
                        f"cx_handbook_compare_{comp_id}",
                    ):
                        all_chunks.append(Chunk(
                            content=part["content"],
                            chunk_type=part["chunk_type"],
                            source_url=source_url,
                            source_id=part["source_id"],
                            topic_tags=tags,
                            product_refs=product_handles,
                            hair_types=[],
                            metadata={"section": "product_comparison", "comparison": comp_id},
                        ))
        
        elif chunk_type == "troubleshooting":
            # Split into individual problem → solution pairs
            pairs = split_troubleshooting_pairs(section_text)
            if pairs:
                for problem_title, pair_text in pairs:
                    product_handles = extract_product_handles(pair_text)
                    tags = infer_tags(pair_text) + ["troubleshooting"]
                    slug = re.sub(r"[^a-z0-9]+", "_", problem_title.lower()).strip("_")[:40]
                    
                    all_chunks.append(Chunk(
                        content=pair_text,
                        chunk_type="troubleshooting",
                        source_url=source_url,
                        source_id=f"cx_handbook_troubleshoot_{slug}",
                        topic_tags=tags,
                        product_refs=product_handles,
                        hair_types=[],
                        metadata={"section": "troubleshooting", "problem": problem_title},
                    ))
            else:
                # Fallback: store whole section
                for part in maybe_split_large_chunk(
                    section_text, "troubleshooting",
                    "cx_handbook_troubleshooting",
                ):
                    all_chunks.append(Chunk(
                        content=part["content"],
                        chunk_type="troubleshooting",
                        source_url=source_url,
                        source_id=part["source_id"],
                        topic_tags=infer_tags(section_text) + ["troubleshooting"],
                        product_refs=extract_product_handles(section_text),
                        hair_types=[],
                        metadata={"section": "troubleshooting"},
                    ))
        
        elif chunk_type == "special_case":
            # Split on table-like rows: "Situation | Response Guidance"
            # Each row is a separate chunk for precise retrieval
            rows = re.split(r"\n(?=[A-Z][a-z].*(?:hair|customer|oiling|frizz|blowdry|scalp|daily|sos|leave|colour|keratin|protein|straight|growth|alopecia|pregnan|children|international))", section_text, flags=re.IGNORECASE)
            
            for row in rows:
                row = row.strip()
                if len(row) < 30:
                    continue
                product_handles = extract_product_handles(row)
                tags = infer_tags(row) + ["special_case"]
                slug = re.sub(r"[^a-z0-9]+", "_", row[:40].lower()).strip("_")
                
                all_chunks.append(Chunk(
                    content=row,
                    chunk_type="special_case",
                    source_url=source_url,
                    source_id=f"cx_handbook_edge_{slug}",
                    topic_tags=tags,
                    product_refs=product_handles,
                    hair_types=[],
                    metadata={"section": "special_cases"},
                ))
        
        elif chunk_type == "escalation_rule":
            # Keep as a single chunk — it's a critical reference the LLM needs whole
            all_chunks.append(Chunk(
                content=section_text,
                chunk_type="escalation_rule",
                source_url=source_url,
                source_id="cx_handbook_escalation_rules",
                topic_tags=["escalation", "support", "flag_rupika"],
                product_refs=[],
                hair_types=[],
                metadata={"section": "escalation_rules"},
            ))
        
        elif chunk_type == "policy":
            # Split into order modifications, delivery issues, returns
            sub_sections = [
                (r"Order Modifications", "order_modifications"),
                (r"Delivery Issues", "delivery_issues"),
                (r"Returns and Refunds", "returns_refunds"),
            ]
            boundaries = []
            for pattern, sub_id in sub_sections:
                match = re.search(pattern, section_text, re.IGNORECASE)
                if match:
                    boundaries.append((match.start(), sub_id))
            boundaries.sort(key=lambda x: x[0])
            
            for i, (start, sub_id) in enumerate(boundaries):
                end = boundaries[i + 1][0] if i + 1 < len(boundaries) else len(section_text)
                sub_text = section_text[start:end].strip()
                
                for part in maybe_split_large_chunk(sub_text, "policy", f"cx_handbook_policy_{sub_id}"):
                    all_chunks.append(Chunk(
                        content=part["content"],
                        chunk_type="policy",
                        source_url=source_url,
                        source_id=part["source_id"],
                        topic_tags=["policy", sub_id.replace("_", " ")],
                        product_refs=[],
                        hair_types=[],
                        metadata={"section": "policy", "sub_section": sub_id},
                    ))
        
        else:
            # Generic handler for remaining sections: tone_guide, quick_reference,
            # hair_type_guide, ingredient_info
            product_handles = extract_product_handles(section_text)
            tags = infer_tags(section_text)
            
            for part in maybe_split_large_chunk(
                section_text, chunk_type,
                f"cx_handbook_{chunk_type}",
            ):
                all_chunks.append(Chunk(
                    content=part["content"],
                    chunk_type=part["chunk_type"],
                    source_url=source_url,
                    source_id=part["source_id"],
                    topic_tags=tags,
                    product_refs=product_handles,
                    hair_types=[],
                    metadata={"section": chunk_type},
                ))
    
    print(f"[cx_handbook] total chunks: {len(all_chunks)}")
    
    # Summary by type
    from collections import Counter
    type_counts = Counter(c.chunk_type for c in all_chunks)
    for ct, count in type_counts.most_common():
        print(f"  {ct:25s}: {count}")
    
    return all_chunks


# ---------------------------------------------------------------------------
# DB write (reuses pattern from hair_type_sheet)
# ---------------------------------------------------------------------------

async def write_chunks_to_db(chunks: list[Chunk], pool) -> int:
    """Write chunks to kb_chunks. Deactivates old cx_handbook chunks first."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            deactivated = await conn.execute(
                "UPDATE kb_chunks SET is_active = FALSE WHERE source_type = 'cx_handbook'"
            )
            print(f"[cx_handbook] deactivated old chunks: {deactivated}")
            
            inserted = 0
            for chunk in chunks:
                await conn.execute("""
                    INSERT INTO kb_chunks (
                        content, source_type, source_url, source_id,
                        chunk_type, topic_tags, product_refs, hair_types,
                        metadata, is_active, version
                    ) VALUES ($1, 'cx_handbook', $2, $3, $4, $5, $6, $7, $8, TRUE, 1)
                """,
                    chunk.content,
                    chunk.source_url,
                    chunk.source_id,
                    chunk.chunk_type,
                    chunk.topic_tags,
                    chunk.product_refs,
                    chunk.hair_types,
                    json.dumps(chunk.metadata),
                )
                inserted += 1
            
            print(f"[cx_handbook] inserted {inserted} chunks")
            return inserted


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Ingest Moxie CX Handbook")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--pdf", help="Path to the CX Handbook PDF")
    group.add_argument("--text", help="Path to pre-extracted text file")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output-json", help="Write chunks to JSON for inspection")
    args = parser.parse_args()
    
    if args.pdf:
        print(f"[cx_handbook] extracting text from {args.pdf} ...")
        text = extract_text_from_pdf(args.pdf)
        print(f"[cx_handbook] extracted {len(text)} chars from PDF")
    else:
        text = Path(args.text).read_text(encoding="utf-8")
        print(f"[cx_handbook] read {len(text)} chars from text file")
    
    chunks = ingest_cx_handbook(text)
    
    if args.output_json:
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
        print(f"[cx_handbook] wrote {len(out)} chunks to {args.output_json}")
    
    if args.dry_run:
        print("\n" + "=" * 80)
        print("DRY RUN — all chunks:")
        print("=" * 80)
        for i, c in enumerate(chunks):
            print(f"\n--- Chunk {i+1} [{c.chunk_type}] ---")
            print(f"Source ID: {c.source_id}")
            print(f"Products: {c.product_refs[:5]}")
            print(f"Hair types: {c.hair_types}")
            print(f"Tags: {c.topic_tags[:8]}")
            print(f"Content ({len(c.content)} chars):")
            print(c.content[:200] + ("..." if len(c.content) > 200 else ""))
        return
    
    import asyncio
    async def _write():
        from app.db import get_pool, close
        pool = await get_pool()
        try:
            count = await write_chunks_to_db(chunks, pool)
            print(f"[cx_handbook] done — {count} chunks written to DB")
        finally:
            await close()
    
    asyncio.run(_write())


if __name__ == "__main__":
    main()
