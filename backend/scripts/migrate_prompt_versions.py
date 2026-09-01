"""One-time migration: add prompt_versions table and prompt_version column to chat_sessions."""

import asyncio
import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))

from app.db import get_pool


async def main():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS prompt_versions (
                fingerprint     TEXT PRIMARY KEY,
                version_bundle  JSONB NOT NULL,
                created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        print("Created prompt_versions table")

        col_exists = await conn.fetchval("""
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'chat_sessions' AND column_name = 'prompt_version'
        """)
        if not col_exists:
            await conn.execute(
                "ALTER TABLE chat_sessions ADD COLUMN prompt_version TEXT"
            )
            print("Added prompt_version column to chat_sessions")

            await conn.execute(
                "CREATE INDEX IF NOT EXISTS chat_sessions_prompt_ver_idx ON chat_sessions (prompt_version)"
            )
            print("Created index on chat_sessions.prompt_version")
        else:
            print("prompt_version column already exists")

    print("Migration complete")


if __name__ == "__main__":
    asyncio.run(main())
