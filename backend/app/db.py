"""Postgres connection pool and schema bootstrap."""

from __future__ import annotations

import json
import os
from pathlib import Path

import asyncpg

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://callagent:callagent@localhost:5433/callagent",
)

SCHEMA_PATH = Path(__file__).parent / "schema.sql"

_pool: asyncpg.Pool | None = None


async def _init_connection(conn: asyncpg.Connection) -> None:
    """Decode jsonb into Python objects rather than handing back raw strings."""
    await conn.set_type_codec(
        "jsonb",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
    )


async def connect() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=1,
            max_size=10,
            init=_init_connection,
        )
    return _pool


async def disconnect() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB pool not initialised — call connect() first")
    return _pool


async def apply_schema() -> None:
    """Idempotent. Runs on startup so a fresh container is usable immediately."""
    p = await connect()
    async with p.acquire() as conn:
        await conn.execute(SCHEMA_PATH.read_text())
