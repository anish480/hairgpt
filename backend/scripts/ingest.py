"""Ingest all data sources into kb_chunks with embeddings.

Run:
    uv run python -m scripts.ingest
"""

import asyncio
import json
import sys
from pathlib import Path

from pgvector.asyncpg import register_vector

from app.db import get_pool, close
from app.llm import embed_batch

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def load_json_chunks(filename: str) -> list[dict]:
    path = DATA_DIR / filename
    if not path.exists():
        print(f"[ingest] SKIP {filename} — file not found")
        return []
    with open(path) as f:
        chunks = json.load(f)
    print(f"[ingest] loaded {len(chunks)} chunks from {filename}")
    return chunks


def _chunk_to_dict(c) -> dict:
    return {
        "content": c.content,
        "source_type": c.source_type,
        "source_url": c.source_url,
        "source_id": c.source_id,
        "chunk_type": c.chunk_type,
        "topic_tags": c.topic_tags,
        "product_refs": c.product_refs,
        "hair_types": c.hair_types,
        "metadata": c.metadata,
    }


def load_products_csv() -> list[dict]:
    csv_path = DATA_DIR / "products_export.csv"
    if not csv_path.exists():
        print("[ingest] SKIP products_export.csv — not found")
        return []
    sys.path.insert(0, str(DATA_DIR))
    from products_csv import ingest_products_csv
    raw_chunks, catalog = ingest_products_csv(str(csv_path))

    catalog_path = DATA_DIR / "product_catalog.json"
    catalog_path.write_text(json.dumps(catalog, indent=2, ensure_ascii=False))
    print(f"[ingest] wrote product catalog to {catalog_path}")

    return [_chunk_to_dict(c) for c in raw_chunks]


def load_hair_type_csv() -> list[dict]:
    candidates = [
        "Hair type and product recommendations - Sheet1.csv",
        "hair_type_recommendations.csv",
    ]
    csv_path = None
    for name in candidates:
        p = DATA_DIR / name
        if p.exists():
            csv_path = p
            break
    if csv_path is None:
        print(f"[ingest] SKIP hair type CSV — not found")
        return []
    sys.path.insert(0, str(DATA_DIR))
    from hair_type_sheet import ingest_hair_type_csv
    raw_chunks = ingest_hair_type_csv(str(csv_path))
    return [_chunk_to_dict(c) for c in raw_chunks]


async def ingest():
    chunks: list[dict] = []
    chunks.extend(load_json_chunks("cx_handbook_chunks.json"))
    chunks.extend(load_json_chunks("video_chunks.json"))
    chunks.extend(load_hair_type_csv())
    chunks.extend(load_products_csv())

    if not chunks:
        print("[ingest] no chunks to ingest")
        return

    print(f"\n[ingest] total chunks to embed: {len(chunks)}")
    texts = [c["content"] for c in chunks]
    embeddings = await embed_batch(texts)
    print(f"[ingest] generated {len(embeddings)} embeddings ({len(embeddings[0])}d)")

    pool = await get_pool()
    async with pool.acquire() as conn:
        await register_vector(conn)
        async with conn.transaction():
            await conn.execute("UPDATE kb_chunks SET is_active = FALSE WHERE is_active = TRUE")
            for chunk, emb in zip(chunks, embeddings):
                await conn.execute(
                    """
                    INSERT INTO kb_chunks
                        (content, embedding, source_type, source_url, source_id,
                         chunk_type, topic_tags, product_refs, hair_types, metadata)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    """,
                    chunk["content"],
                    emb,
                    chunk.get("source_type", ""),
                    chunk.get("source_url", ""),
                    chunk.get("source_id", ""),
                    chunk.get("chunk_type", ""),
                    chunk.get("topic_tags", []),
                    chunk.get("product_refs", []),
                    chunk.get("hair_types", []),
                    json.dumps(chunk.get("metadata", {})),
                )
    print(f"[ingest] inserted {len(chunks)} chunks with embeddings")

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT count(*) as n FROM kb_chunks WHERE is_active"
        )
        print(f"[ingest] active chunks in DB: {row['n']}")
        rows = await conn.fetch(
            "SELECT source_type, count(*) as n FROM kb_chunks WHERE is_active GROUP BY source_type"
        )
        for r in rows:
            print(f"  {r['source_type']}: {r['n']}")

    await close()
    print("[ingest] done")


if __name__ == "__main__":
    asyncio.run(ingest())
