from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Dict, List, Optional, Tuple
import aiomysql
from app.config import settings

logger = logging.getLogger(__name__)

_pool: Optional[aiomysql.Pool] = None


async def init_db_pool() -> aiomysql.Pool:
    global _pool
    current_loop = asyncio.get_running_loop()
    if _pool is not None:
        try:
            if _pool._loop.is_closed() or _pool._loop is not current_loop:
                _pool = None
        except Exception:
            _pool = None

    if _pool is None:
        kwargs: Dict[str, Any] = {
            "user": settings.DB_USER,
            "password": settings.DB_PASSWORD,
            "db": settings.DB_NAME,
            "minsize": settings.DB_POOL_MIN_SIZE,
            "maxsize": settings.DB_POOL_MAX_SIZE,
            "autocommit": True,
            "cursorclass": aiomysql.DictCursor,
        }
        if settings.DB_SOCKET and os.path.exists(settings.DB_SOCKET):
            kwargs["unix_socket"] = settings.DB_SOCKET
        else:
            kwargs["host"] = settings.DB_HOST
            kwargs["port"] = settings.DB_PORT

        _pool = await aiomysql.create_pool(**kwargs)
        logger.info(f"Database pool initialized: {settings.DB_NAME} (max_size={settings.DB_POOL_MAX_SIZE})")
    return _pool


async def close_db_pool() -> None:
    global _pool
    if _pool is not None:
        try:
            if not _pool._loop.is_closed():
                _pool.close()
                await _pool.wait_closed()
        except Exception:
            pass
        finally:
            _pool = None
        logger.info("Database pool closed cleanly.")


async def execute_query(query: str, params: Optional[Tuple[Any, ...]] = None) -> List[Dict[str, Any]]:
    """Executes a read query using strict parameter binding."""
    pool = await init_db_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(query, params or ())
            rows = await cur.fetchall()
            return list(rows)


async def execute_query_one(query: str, params: Optional[Tuple[Any, ...]] = None) -> Optional[Dict[str, Any]]:
    """Executes a read query returning a single row."""
    pool = await init_db_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(query, params or ())
            row = await cur.fetchone()
            return dict(row) if row else None


async def execute_write(query: str, params: Optional[Tuple[Any, ...]] = None) -> int:
    """Executes an INSERT, UPDATE, or DELETE query and returns lastrowid or affected rows."""
    pool = await init_db_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, params or ())
            return cur.lastrowid or cur.rowcount


async def check_db_health() -> bool:
    try:
        res = await execute_query_one("SELECT 1 as healthy")
        return bool(res and res.get("healthy") == 1)
    except Exception as exc:
        logger.error(f"MySQL healthcheck failed: {exc}")
        return False
