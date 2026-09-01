"""One-time migration: add hairgpt_events and hairgpt_conversions tables."""

import asyncio
import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))

from app.db import get_pool

EVENTS_DDL = """
CREATE TABLE IF NOT EXISTS hairgpt_events (
    id          BIGSERIAL PRIMARY KEY,
    session_id  TEXT NOT NULL,
    event       TEXT NOT NULL,
    payload     JSONB DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

CONVERSIONS_DDL = """
CREATE TABLE IF NOT EXISTS hairgpt_conversions (
    id                BIGSERIAL PRIMARY KEY,
    session_id        TEXT NOT NULL,
    shopify_order_id  TEXT NOT NULL UNIQUE,
    order_number      TEXT,
    order_total       NUMERIC(10,2),
    hairgpt_revenue   NUMERIC(10,2),
    hairgpt_items     INT,
    total_items       INT,
    order_created_at  TIMESTAMPTZ,
    reconciled_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


async def main():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(EVENTS_DDL)
        await conn.execute("CREATE INDEX IF NOT EXISTS hairgpt_events_session_idx ON hairgpt_events (session_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS hairgpt_events_event_idx ON hairgpt_events (event, created_at)")
        print("Created hairgpt_events table + indexes")

        await conn.execute(CONVERSIONS_DDL)
        await conn.execute("CREATE INDEX IF NOT EXISTS hairgpt_conv_session_idx ON hairgpt_conversions (session_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS hairgpt_conv_order_date_idx ON hairgpt_conversions (order_created_at)")
        print("Created hairgpt_conversions table + indexes")


if __name__ == "__main__":
    asyncio.run(main())
