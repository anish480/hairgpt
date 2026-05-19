"""Ingest video tutorial metadata into kb_chunks.

These are Moxie's WhatsApp tutorial videos stored in Google Drive.
Each video maps to one or more products/routines. The bot links to these
when a customer asks "how do I use X?" or "show me how the wavy routine works."

The metadata is hardcoded here because there are only 9 videos and they change
rarely. When new videos are added, update the VIDEO_CATALOGUE list below.

Once YouTube URLs are available, update the `public_url` field for each video.
Drive links work but are not ideal for customer-facing use.

Run:
    uv run python -m app.ingest.videos [--dry-run]
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path

from app.ingest.hair_type_sheet import Chunk


# ---------------------------------------------------------------------------
# Video catalogue — update this when videos are added or URLs change
# ---------------------------------------------------------------------------

@dataclass
class VideoMeta:
    """Metadata for a single tutorial video."""
    title: str
    drive_id: str
    description: str
    products: list[str]          # canonical Shopify handles
    routines: list[str]          # routine IDs matching recommendation engine
    hair_types: list[str]        # applicable hair types (empty = all)
    topic_tags: list[str]
    public_url: str = ""         # YouTube/IG URL once uploaded; empty = use drive_url
    
    @property
    def drive_url(self) -> str:
        return f"https://drive.google.com/file/d/{self.drive_id}/view"
    
    @property
    def best_url(self) -> str:
        return self.public_url or self.drive_url


VIDEO_CATALOGUE: list[VideoMeta] = [
    VideoMeta(
        title="Wavy Hair Routine Tutorial",
        drive_id="18jTvxFhoViR-xTYfPAgDDrmGtuFoTYej",
        description="Complete 4-step Moxie wavy hair routine: shampoo, condition, leave-in on soaking wet hair, gel application, scrunch technique, and drying tips.",
        products=[
            "gentle-cleansing-shampoo",
            "ultra-hydrating-conditioner",
            "weightless-leave-in-conditioner",
            "flexi-styling-serum-gel",
        ],
        routines=["wavy_full"],
        hair_types=["2a", "2b", "2c"],
        topic_tags=["waves", "frizz", "hold", "hydration", "routine", "tutorial"],
    ),
    VideoMeta(
        title="Curly Hair Routine Tutorial",
        drive_id="19LICTkyrDFxRyEmGj5jpq95kmvP4FqAL",
        description="Complete 4-step Moxie curly hair routine: shampoo, condition, curl cream on soaking wet hair, gel application, scrunching for curl clumping, and diffusing tips.",
        products=[
            "gentle-cleansing-shampoo",
            "ultra-hydrating-conditioner",
            "super-defining-curl-cream",
            "flexi-styling-serum-gel",
        ],
        routines=["curly_full"],
        hair_types=["3a", "3b", "3c"],
        topic_tags=["curls", "frizz", "hold", "hydration", "routine", "tutorial"],
    ),
    VideoMeta(
        title="Kartik's Curly Hair Tutorial",
        drive_id="1z74gnKGqpUNrCei7HLaEUt-b1VkcDfOC",
        description="Curly hair routine demonstrated on men's curly hair. Shows the full Moxie curly routine with tips for shorter curly hair.",
        products=[
            "gentle-cleansing-shampoo",
            "ultra-hydrating-conditioner",
            "super-defining-curl-cream",
            "flexi-styling-serum-gel",
        ],
        routines=["curly_full"],
        hair_types=["3a", "3b"],
        topic_tags=["curls", "frizz", "men", "short_hair", "routine", "tutorial"],
    ),
    VideoMeta(
        title="Ditch the Frizz Trio (DTFT) Tutorial",
        drive_id="1BUwCbTqZ3SpAOnXKGNQCgV42bD1A9lUO",
        description="How to use the Moxie Ditch the Frizz Trio: gentle cleansing shampoo, ultra hydrating conditioner, and frizz fighting hair serum for frizz-free smooth hair.",
        products=[
            "gentle-cleansing-shampoo",
            "ultra-hydrating-conditioner",
            "frizz-fighting-hair-serum",
        ],
        routines=["dtft"],
        hair_types=["1b", "1c", "2a"],
        topic_tags=["frizz", "fine_hair", "hydration", "routine", "tutorial"],
    ),
    VideoMeta(
        title="HydroRepair Routine (THRR) Tutorial",
        drive_id="1bM1ecsanr59tlbMovw8j61K1OofDEXPH",
        description="How to use the Moxie HydroRepair routine for damaged, colour-treated, or heat-damaged hair: HA shampoo, HA conditioner, and HA hair serum.",
        products=[
            "hyaluronic-acid-repairing-shampoo",
            "hyaluronic-acid-repairing-conditioner",
            "hyaluronic-acid-repairing-serum",
        ],
        routines=["hydrorepair"],
        hair_types=[],
        topic_tags=["damage", "repair", "colour_treated", "chemically_treated", "hydration", "routine", "tutorial"],
    ),
    VideoMeta(
        title="Dry Shampoo Tutorial",
        drive_id="1xbARCdsD3G1cGP3g_KMoIwiuNcId0FAj",
        description="How to use Moxie Cheat Day Dry Shampoo: spray at roots, wait, blend with the brush for a between-wash refresh.",
        products=["cheat-day-dry-shampoo"],
        routines=[],
        hair_types=[],
        topic_tags=["dry_shampoo", "refresh", "oily_scalp", "tutorial"],
    ),
    VideoMeta(
        title="On The Fly (OTF) Hair Finishing Stick Tutorial",
        drive_id="1bGtZHmkXuPlSjtcst9WdqriHV3SL8R0b",
        description="How to use the Moxie On The Fly hair finishing stick for taming flyaways, baby hairs, and light frizz on dry styled hair.",
        products=["on-the-fly-hair-finishing-stick"],
        routines=[],
        hair_types=[],
        topic_tags=["flyaways", "styling", "finishing", "tutorial"],
    ),
    VideoMeta(
        title="Headliner Wax Stick (HWS) Tutorial",
        drive_id="1QPu_v0EVa1V6JTbSruinIXkTkF3TQAjb",
        description="How to use the Moxie Headliner Hair Wax Stick with the finishing brush for sleek looks, edge control, and strong hold styling on dry hair.",
        products=["headliner-hair-wax-stick", "hair-finishing-brush"],
        routines=[],
        hair_types=[],
        topic_tags=["styling", "sleek", "hold", "edge_control", "tutorial"],
    ),
    VideoMeta(
        title="Heat Protection Spray (HPS) Tutorial",
        drive_id="1dimr9FJUrFPJXPaR8k12a0QB_lZutLmz",
        description="How to use Moxie Firefighter Heat Protection Spray before blow drying or heat styling: 2 pumps on mid-lengths, applied by hand on damp hair before heat.",
        products=["firefighter-heat-protection-spray"],
        routines=[],
        hair_types=[],
        topic_tags=["heat_styling", "heat_protection", "styling", "tutorial"],
    ),
]


# ---------------------------------------------------------------------------
# Chunk generation
# ---------------------------------------------------------------------------

def generate_video_chunks() -> list[Chunk]:
    """Generate one KB chunk per video."""
    chunks: list[Chunk] = []
    
    for video in VIDEO_CATALOGUE:
        # Build the content the LLM will see during retrieval
        content_parts = [
            f"Tutorial video: {video.title}",
            f"\n{video.description}",
            f"\nWatch here: {video.best_url}",
        ]
        if video.products:
            content_parts.append(f"\nProducts featured: {', '.join(video.products)}")
        if video.routines:
            content_parts.append(f"\nRoutine: {', '.join(video.routines)}")
        if video.hair_types:
            content_parts.append(f"\nBest for hair types: {', '.join(video.hair_types)}")
        
        chunks.append(Chunk(
            content="\n".join(content_parts),
            source_type="video_tutorial",
            source_url=video.best_url,
            source_id=f"video_{video.drive_id[:12]}",
            chunk_type="video_tutorial",
            topic_tags=video.topic_tags,
            product_refs=video.products,
            hair_types=video.hair_types,
            metadata={
                "drive_id": video.drive_id,
                "drive_url": video.drive_url,
                "public_url": video.public_url,
                "routines": video.routines,
                "title": video.title,
            },
        ))
    
    return chunks


# ---------------------------------------------------------------------------
# DB write
# ---------------------------------------------------------------------------

async def write_chunks_to_db(chunks: list[Chunk], pool) -> int:
    """Write video chunks to kb_chunks. Deactivates old video chunks first."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            deactivated = await conn.execute(
                "UPDATE kb_chunks SET is_active = FALSE WHERE source_type = 'video_tutorial'"
            )
            print(f"[videos] deactivated old chunks: {deactivated}")
            
            inserted = 0
            for chunk in chunks:
                await conn.execute("""
                    INSERT INTO kb_chunks (
                        content, source_type, source_url, source_id,
                        chunk_type, topic_tags, product_refs, hair_types,
                        metadata, is_active, version
                    ) VALUES ($1, 'video_tutorial', $2, $3, $4, $5, $6, $7, $8, TRUE, 1)
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
            
            print(f"[videos] inserted {inserted} chunks")
            return inserted


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Ingest video tutorial metadata")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output-json", help="Write chunks to JSON for inspection")
    args = parser.parse_args()
    
    chunks = generate_video_chunks()
    print(f"[videos] generated {len(chunks)} video chunks")
    
    for c in chunks:
        print(f"  {c.metadata['title']:45s} | products={len(c.product_refs)} | {c.hair_types}")
    
    if args.output_json:
        out = [
            {
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
            for c in chunks
        ]
        Path(args.output_json).write_text(json.dumps(out, indent=2))
        print(f"[videos] wrote to {args.output_json}")
    
    if args.dry_run:
        print("\n" + "=" * 80)
        for i, c in enumerate(chunks):
            print(f"\n--- Video {i+1}: {c.metadata['title']} ---")
            print(c.content)
        return
    
    import asyncio
    async def _write():
        from app.db import get_pool, close
        pool = await get_pool()
        try:
            count = await write_chunks_to_db(chunks, pool)
            print(f"[videos] done — {count} chunks written to DB")
        finally:
            await close()
    
    asyncio.run(_write())


if __name__ == "__main__":
    main()
