"""End-to-end smoke test: Vertex AI + Shopify Admin API + Secret Manager.

Run from the backend/ directory:
    uv run python -m scripts.smoke
"""

import asyncio
import sys

from app import db
from app.clients.shopify import admin_graphql, mint_admin_token
from app.config import settings
from app.llm import FLASH, generate


async def check_shopify() -> None:
    print(f"[shopify] minting token for {settings.shopify_shop}.myshopify.com ...")
    token = await mint_admin_token()
    print(f"[shopify] token OK (length={len(token)})")

    data = await admin_graphql("{ shop { name myshopifyDomain } }")
    name = data["data"]["shop"]["name"]
    print(f"[shopify] admin graphql OK — shop name: {name}")


async def check_vertex() -> None:
    print(f"[vertex] sending prompt to {FLASH} in {settings.gcp_location} ...")
    text = await generate(
        "Reply with exactly two words: hello hairgpt",
        model=FLASH,
        max_tokens=64,
        thinking_budget=0,
    )
    print(f"[vertex] response: {text.strip()!r}")


async def check_db() -> None:
    print(f"[db] connecting to {settings.db_instance} ...")
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        version = await conn.fetchval("SELECT version()")
        extensions = await conn.fetch(
            "SELECT extname FROM pg_extension WHERE extname IN ('vector','pg_trgm','pgcrypto') ORDER BY extname"
        )
        tables = await conn.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
        )
    print(f"[db] {version.split(',')[0]}")
    print(f"[db] extensions: {[r['extname'] for r in extensions]}")
    print(f"[db] tables: {[r['tablename'] for r in tables]}")
    await db.close()


async def main() -> None:
    failed = False
    for name, check in [("shopify", check_shopify), ("vertex", check_vertex), ("db", check_db)]:
        try:
            await check()
        except Exception as e:
            print(f"[{name}] FAILED: {e}", file=sys.stderr)
            failed = True

    if failed:
        sys.exit(1)
    print("\n[smoke] all pipes OK")


if __name__ == "__main__":
    asyncio.run(main())
