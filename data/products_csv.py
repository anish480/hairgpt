"""Parse Shopify products_export.csv into kb_chunks.

Run standalone for inspection:
    python data/products_csv.py --dry-run

Called by backend/scripts/ingest.py during normal ingestion.
"""

from __future__ import annotations

import csv
import html
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

# Column name aliases (Shopify export includes metafield paths in parens)
COL_HANDLE = "Handle"
COL_TITLE = "Title"
COL_BODY = "Body (HTML)"
COL_TYPE = "Type"
COL_TAGS = "Tags"
COL_PRICE = "Variant Price"
COL_COMPARE_PRICE = "Variant Compare At Price"
COL_IMAGE = "Image Src"
COL_COLLECTION = "Collection Name (product.metafields.custom.collection_name)"
COL_BENEFITS = "Benefits Text (product.metafields.custom.benefits_text)"
COL_HAIR_TYPE = "Hair  Type (product.metafields.custom.hair_type)"
COL_ROUTINE = "Routine (product.metafields.custom.routine_new)"
COL_HOW_TO = "How to use (product.metafields.custom.how_to_use)"
COL_INGREDIENTS_HEADING = "Ingredients Heading (product.metafields.custom.ingredients_heading)"
COL_INGREDIENTS_SUB = "Ingredients Sub-text (product.metafields.custom.ingredients_sub_text)"
COL_FAQ_Q = "FAQs Question (product.metafields.custom.faqs_question)"
COL_FAQ_A = "FAQs Answer (product.metafields.custom.faqs_answer)"
COL_SUITABLE = "Suitable for hair type (product.metafields.shopify.suitable-for-hair-type)"
COL_COMPLEMENTARY = "Complementary products (product.metafields.shopify--discovery--product_recommendation.complementary_products)"
COL_RELATED = "Related products (product.metafields.shopify--discovery--product_recommendation.related_products)"

HAIR_TYPE_MAP = {
    "straight": ["1a", "1b", "1c"],
    "wavy": ["2a", "2b", "2c"],
    "curly": ["3a", "3b", "3c"],
    "coily": ["4a", "4b", "4c"],
    "frizzy": ["2a", "2b", "2c", "3a", "3b", "3c"],
    "dry": [],
    "damaged": [],
    "oily": [],
    "normal": [],
    "fine": [],
    "thick": [],
    "all": ["1a", "1b", "1c", "2a", "2b", "2c", "3a", "3b", "3c", "4a", "4b", "4c"],
}


def strip_html(text: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _get(row: dict, col: str) -> str:
    return (row.get(col) or "").strip()


def parse_hair_types(raw: str) -> list[str]:
    if not raw:
        return []
    types: set[str] = set()
    for part in re.split(r"[\n;,]+", raw):
        key = part.strip().lower()
        for mapped in HAIR_TYPE_MAP.get(key, []):
            types.add(mapped)
    return sorted(types)


def parse_tags(raw: str) -> list[str]:
    if not raw:
        return []
    return [t.strip().lower().replace(" ", "_") for t in raw.split(",") if t.strip()]


def format_price(raw: str) -> str:
    if not raw:
        return ""
    try:
        p = float(raw)
        return f"₹{int(p)}" if p == int(p) else f"₹{p:.2f}"
    except ValueError:
        return raw


@dataclass
class Chunk:
    content: str
    source_type: str = "shopify_product"
    source_url: str = ""
    source_id: str = ""
    chunk_type: str = ""
    topic_tags: list[str] = field(default_factory=list)
    product_refs: list[str] = field(default_factory=list)
    hair_types: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


def deduplicate_by_handle(rows: list[dict]) -> dict[str, dict]:
    products: dict[str, dict] = {}
    for row in rows:
        handle = _get(row, COL_HANDLE)
        if not handle:
            continue
        if handle not in products:
            products[handle] = row
        else:
            existing = products[handle]
            if not _get(existing, COL_TITLE) and _get(row, COL_TITLE):
                products[handle] = row
            if not _get(existing, COL_IMAGE) and _get(row, COL_IMAGE):
                existing[COL_IMAGE] = row[COL_IMAGE]
    return products


def generate_chunks(handle: str, row: dict) -> list[Chunk]:
    chunks: list[Chunk] = []
    title = _get(row, COL_TITLE)
    if not title:
        return chunks

    body = strip_html(_get(row, COL_BODY))
    price = format_price(_get(row, COL_PRICE))
    compare_price = format_price(_get(row, COL_COMPARE_PRICE))
    collection = _get(row, COL_COLLECTION)
    benefits = _get(row, COL_BENEFITS)
    hair_type_raw = _get(row, COL_HAIR_TYPE)
    routine = _get(row, COL_ROUTINE)
    tags_raw = _get(row, COL_TAGS)
    image = _get(row, COL_IMAGE)
    product_type = _get(row, COL_TYPE)

    hair_types = parse_hair_types(hair_type_raw)
    topic_tags = parse_tags(tags_raw)
    url = f"https://moxiebeauty.in/products/{handle}"

    base_meta = {
        "product_type": product_type,
        "image_src": image,
        "collection": collection,
        "routine": routine,
    }

    # --- Chunk 1: Product Overview ---
    parts = [f"{title}"]
    if product_type:
        parts.append(f"Category: {product_type}")
    if price:
        price_str = price
        if compare_price and compare_price != price:
            price_str = f"{price} (MRP {compare_price})"
        parts.append(f"Price: {price_str}")
    if collection:
        parts.append(f"Collection: {collection}")
    if body:
        parts.append(f"\n{body}")
    if benefits:
        benefits_lines = [b.strip() for b in benefits.split("\n") if b.strip()]
        parts.append("\nKey benefits:\n" + "\n".join(f"- {b}" for b in benefits_lines))
    if hair_type_raw:
        parts.append(f"\nSuitable for: {hair_type_raw.replace(chr(10), ', ')}")
    if routine:
        parts.append(f"Part of: {routine.replace(chr(10), ', ')} routine(s)")

    chunks.append(Chunk(
        content="\n".join(parts),
        chunk_type="product_overview",
        source_url=url,
        source_id=f"product_{handle}",
        topic_tags=topic_tags,
        product_refs=[handle],
        hair_types=hair_types,
        metadata={**base_meta, "price": price},
    ))

    # --- Chunk 2: Usage + Ingredients ---
    how_to = _get(row, COL_HOW_TO)
    ingredients_heading = _get(row, COL_INGREDIENTS_HEADING)
    ingredients_sub = _get(row, COL_INGREDIENTS_SUB)

    if how_to or ingredients_heading:
        usage_parts = [f"{title} — Usage & Ingredients"]
        if how_to:
            usage_parts.append(f"\nHow to use:\n{how_to}")
        if ingredients_heading:
            headings = [h.strip() for h in ingredients_heading.split("\n") if h.strip()]
            subs = [s.strip() for s in (ingredients_sub or "").split("\n") if s.strip()]
            if headings:
                usage_parts.append("\nKey ingredients:")
                for i, h in enumerate(headings):
                    if "aqua" in h.lower() or len(h) > 100:
                        break
                    line = f"- {h}"
                    if i < len(subs):
                        line += f" — {subs[i]}"
                    usage_parts.append(line)

        chunks.append(Chunk(
            content="\n".join(usage_parts),
            chunk_type="product_usage",
            source_url=url,
            source_id=f"product_{handle}_usage",
            topic_tags=topic_tags,
            product_refs=[handle],
            hair_types=hair_types,
            metadata=base_meta,
        ))

    # --- Chunk 3: FAQs ---
    faq_q = _get(row, COL_FAQ_Q)
    faq_a = _get(row, COL_FAQ_A)

    if faq_q and faq_a:
        questions = [q.strip() for q in faq_q.split("\n") if q.strip()]
        answers = [a.strip() for a in faq_a.split("\n") if a.strip()]
        pairs = list(zip(questions, answers))
        if pairs:
            faq_parts = [f"{title} — Frequently Asked Questions\n"]
            for q, a in pairs:
                faq_parts.append(f"Q: {q}\nA: {a}\n")

            chunks.append(Chunk(
                content="\n".join(faq_parts),
                chunk_type="product_faq",
                source_url=url,
                source_id=f"product_{handle}_faq",
                topic_tags=topic_tags,
                product_refs=[handle],
                hair_types=hair_types,
                metadata=base_meta,
            ))

    return chunks


def generate_product_catalog(products: dict[str, dict]) -> dict[str, dict]:
    catalog = {}
    for handle, row in products.items():
        title = _get(row, COL_TITLE)
        if not title:
            continue
        body = strip_html(_get(row, COL_BODY))
        catalog[handle] = {
            "name": title,
            "price": format_price(_get(row, COL_PRICE)),
            "url": f"https://moxiebeauty.in/products/{handle}",
            "description": body[:200] if body else "",
            "type": _get(row, COL_TYPE),
            "image_src": _get(row, COL_IMAGE),
        }
    return catalog


def ingest_products_csv(csv_path: str) -> tuple[list[Chunk], dict[str, dict]]:
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"[products] parsed {len(rows)} rows from {csv_path}")

    products = deduplicate_by_handle(rows)
    print(f"[products] deduplicated to {len(products)} unique products")

    all_chunks: list[Chunk] = []
    for handle, row in products.items():
        chunks = generate_chunks(handle, row)
        all_chunks.extend(chunks)

    print(f"[products] generated {len(all_chunks)} chunks")

    catalog = generate_product_catalog(products)
    print(f"[products] generated catalog with {len(catalog)} products")

    return all_chunks, catalog


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default=str(Path(__file__).parent / "products_export.csv"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output-json", help="Write chunks to JSON")
    parser.add_argument("--output-catalog", help="Write catalog to JSON")
    args = parser.parse_args()

    chunks, catalog = ingest_products_csv(args.csv)

    if args.output_json:
        out = [{"content": c.content, "source_type": c.source_type, "source_url": c.source_url,
                "source_id": c.source_id, "chunk_type": c.chunk_type, "topic_tags": c.topic_tags,
                "product_refs": c.product_refs, "hair_types": c.hair_types, "metadata": c.metadata}
               for c in chunks]
        Path(args.output_json).write_text(json.dumps(out, indent=2))

    if args.output_catalog:
        Path(args.output_catalog).write_text(json.dumps(catalog, indent=2))

    if args.dry_run:
        print(f"\n{'='*60}\nSample chunks:\n{'='*60}")
        for c in chunks[:6]:
            print(f"\n--- [{c.chunk_type}] {c.source_id} ---")
            print(f"Products: {c.product_refs} | Hair types: {c.hair_types}")
            print(f"Tags: {c.topic_tags}")
            print(c.content[:400] + ("..." if len(c.content) > 400 else ""))
