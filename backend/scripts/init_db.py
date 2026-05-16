"""One-shot DB initializer.

Connects as the `postgres` superuser to apply infra/schemas/postgres.sql
(extensions + tables + indexes) and grant access to the app user.

Run from the backend/ directory:
    uv run python -m scripts.init_db
"""

from __future__ import annotations

import asyncio
import pathlib
import sys

from google.cloud.sql.connector import IPTypes, create_async_connector

from app.clients.secret_manager import get_secret
from app.config import settings

POSTGRES_PASSWORD_SECRET = "db-postgres-password"
SCHEMA_PATH = pathlib.Path(__file__).resolve().parents[2] / "infra/schemas/postgres.sql"

GRANTS = """
GRANT CONNECT ON DATABASE hairgpt TO "hairgpt-app";
GRANT USAGE, CREATE ON SCHEMA public TO "hairgpt-app";
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "hairgpt-app";
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO "hairgpt-app";
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "hairgpt-app";
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO "hairgpt-app";
"""


async def main() -> None:
    schema_sql = SCHEMA_PATH.read_text()
    if not schema_sql.strip():
        print(f"[init_db] schema file empty: {SCHEMA_PATH}", file=sys.stderr)
        sys.exit(1)

    pg_password = get_secret(POSTGRES_PASSWORD_SECRET)
    connector = await create_async_connector()

    try:
        conn = await connector.connect_async(
            settings.db_instance,
            "asyncpg",
            user="postgres",
            password=pg_password,
            db=settings.db_name,
            ip_type=IPTypes.PUBLIC,
        )
        try:
            print(f"[init_db] applying {SCHEMA_PATH.relative_to(SCHEMA_PATH.parents[2])} ...")
            await conn.execute(schema_sql)
            print("[init_db] schema applied")

            print("[init_db] granting privileges to hairgpt-app ...")
            await conn.execute(GRANTS)
            print("[init_db] grants applied")

            tables = await conn.fetch(
                "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
            )
            exts = await conn.fetch(
                "SELECT extname FROM pg_extension WHERE extname IN ('vector','pg_trgm','pgcrypto') ORDER BY extname"
            )
            print(f"[init_db] tables: {[r['tablename'] for r in tables]}")
            print(f"[init_db] extensions: {[r['extname'] for r in exts]}")
        finally:
            await conn.close()
    finally:
        await connector.close_async()

    print("[init_db] done")


if __name__ == "__main__":
    asyncio.run(main())
