from dataclasses import dataclass

from pgvector.asyncpg import register_vector

from app.db import get_pool
from app.llm import embed


@dataclass
class RetrievedChunk:
    id: int
    content: str
    chunk_type: str
    source_id: str
    product_refs: list[str]
    hair_types: list[str]
    score: float


async def retrieve(query: str, top_k: int = 5) -> list[RetrievedChunk]:
    query_emb = (await embed([query]))[0]
    pool = await get_pool()
    async with pool.acquire() as conn:
        await register_vector(conn)
        rows = await conn.fetch(
            """
            WITH vec AS (
                SELECT id, content, chunk_type, source_id, product_refs, hair_types,
                       1 - (embedding <=> $1::vector) AS vec_score
                FROM kb_chunks
                WHERE is_active
                ORDER BY embedding <=> $1::vector
                LIMIT 30
            ),
            fts AS (
                SELECT id,
                       ts_rank_cd(content_tsv, plainto_tsquery('english', $2)) AS fts_score
                FROM kb_chunks
                WHERE is_active AND content_tsv @@ plainto_tsquery('english', $2)
                LIMIT 30
            )
            SELECT v.id, v.content, v.chunk_type, v.source_id,
                   v.product_refs, v.hair_types,
                   v.vec_score * 0.7 + COALESCE(f.fts_score, 0) * 0.3 AS score
            FROM vec v
            LEFT JOIN fts f ON v.id = f.id
            ORDER BY score DESC
            LIMIT $3
            """,
            query_emb,
            query,
            top_k,
        )
    return [
        RetrievedChunk(
            id=r["id"],
            content=r["content"],
            chunk_type=r["chunk_type"],
            source_id=r["source_id"] or "",
            product_refs=list(r["product_refs"] or []),
            hair_types=list(r["hair_types"] or []),
            score=float(r["score"] or 0),
        )
        for r in rows
    ]


def format_retrieval_context(chunks: list[RetrievedChunk]) -> str:
    parts = []
    for i, c in enumerate(chunks, 1):
        label = c.chunk_type.replace("_", " ").title()
        parts.append(f"[{label}] {c.content}")
    return "\n\n---\n\n".join(parts)
