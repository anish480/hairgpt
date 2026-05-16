"""Async Cloud SQL Postgres client using Cloud SQL Python Connector + asyncpg.

Uses the connector for both local dev (with ADC) and Cloud Run (with runtime SA).
No IP allowlist, no Auth Proxy required from the app — TLS + IAM-authenticated tunnel.
"""

from __future__ import annotations

import asyncpg
from google.cloud.sql.connector import Connector, IPTypes, create_async_connector

from app.clients.secret_manager import get_secret
from app.config import settings

_connector: Connector | None = None
_pool: asyncpg.Pool | None = None


async def _get_connector() -> Connector:
    global _connector
    if _connector is None:
        _connector = await create_async_connector()
    return _connector


async def _connect(*_args, **_kwargs) -> asyncpg.Connection:
    # asyncpg.create_pool(connect=...) passes extra kwargs (e.g. `loop`) we ignore.
    connector = await _get_connector()
    password = get_secret(settings.db_password_secret)
    return await connector.connect_async(
        settings.db_instance,
        "asyncpg",
        user=settings.db_user,
        password=password,
        db=settings.db_name,
        ip_type=IPTypes.PUBLIC,
    )


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            connect=_connect,
            min_size=1,
            max_size=5,
        )
    return _pool


async def close() -> None:
    global _pool, _connector
    if _pool is not None:
        await _pool.close()
        _pool = None
    if _connector is not None:
        await _connector.close_async()
        _connector = None
