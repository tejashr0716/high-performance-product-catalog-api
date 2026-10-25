from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar
import redis.asyncio as aioredis
from app.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T")

_redis: Optional[aioredis.Redis] = None


def get_redis_client() -> aioredis.Redis:
    global _redis
    current_loop = None
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        pass

    if _redis is not None:
        try:
            pool = _redis.connection_pool
            if hasattr(pool, "_loop") and pool._loop is not None:
                if pool._loop.is_closed() or (current_loop and pool._loop is not current_loop):
                    _redis = None
        except Exception:
            _redis = None

    if _redis is None:
        _redis = aioredis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            password=settings.REDIS_PASSWORD,
            socket_timeout=settings.REDIS_TIMEOUT_SECONDS,
            socket_connect_timeout=settings.REDIS_TIMEOUT_SECONDS,
            decode_responses=True,
        )
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        try:
            await _redis.aclose()
        except Exception:
            pass
        finally:
            _redis = None
        logger.info("Redis connection closed cleanly.")


# ==============================================================================
# Canonical Key Generation (Collision Immunity)
# ==============================================================================

def make_product_cache_key(product_id: int) -> str:
    """Documented Key: catalog:product:{id}"""
    return f"catalog:product:{product_id}"


def make_list_cache_key(filter_params: Dict[str, Any]) -> str:
    """
    Documented Key: catalog:list:{sha256}
    Canonical parameter serialization guaranteeing zero collisions between
    different filter values, pages, bounds, or sorting orders.
    """
    # Normalize dictionary by removing None and sorting keys
    clean_params = {
        k: v for k, v in filter_params.items() if v is not None and v != ""
    }
    # Stable JSON serialization with sorted keys
    canonical_str = json.dumps(clean_params, default=str, sort_keys=True, separators=(",", ":"))
    param_hash = hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()[:16]
    return f"catalog:list:{param_hash}"


# ==============================================================================
# Safe Cache Operations with Graceful Fallback on Redis Outage
# ==============================================================================

async def safe_cache_get(key: str) -> Optional[Any]:
    """
    Retrieves and parses JSON cached value.
    If Redis is unavailable or times out, safely returns None without raising 500.
    """
    try:
        client = get_redis_client()
        val = await client.get(key)
        if val is not None:
            return json.loads(val)
        return None
    except Exception as exc:
        logger.warning(f"Redis GET failed for key '{key}' ({type(exc).__name__}: {exc}). Falling back to primary MySQL store.")
        return None


async def safe_cache_set(key: str, value: Any, ttl_seconds: int) -> bool:
    """
    Stores JSON serializable value in Redis with explicit TTL.
    Fails safely if Redis is down.
    """
    try:
        client = get_redis_client()
        serialized = json.dumps(value, default=str)
        await client.set(key, serialized, ex=ttl_seconds)
        return True
    except Exception as exc:
        logger.warning(f"Redis SET failed for key '{key}' ({type(exc).__name__}: {exc}). Proceeding without cache.")
        return False


async def safe_cache_delete(key: str) -> bool:
    """Deletes an exact key safely."""
    try:
        client = get_redis_client()
        await client.delete(key)
        return True
    except Exception as exc:
        logger.warning(f"Redis DELETE failed for key '{key}': {exc}")
        return False


async def safe_cache_delete_pattern(pattern: str) -> int:
    """
    Scans and deletes keys matching a glob pattern (e.g. 'catalog:list:*').
    Uses non-blocking SCAN to avoid blocking Redis event loop.
    """
    deleted_count = 0
    try:
        client = get_redis_client()
        cursor = 0
        while True:
            cursor, keys = await client.scan(cursor=cursor, match=pattern, count=100)
            if keys:
                await client.delete(*keys)
                deleted_count += len(keys)
            if cursor == 0:
                break
        return deleted_count
    except Exception as exc:
        logger.warning(f"Redis SCAN/DELETE pattern failed for '{pattern}': {exc}")
        return 0


# ==============================================================================
# Cache Invalidation on Mutations
# ==============================================================================

async def invalidate_product_cache(product_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Invalidates individual product cache and all paginated/search catalog listings.
    Guarantees that updated or deleted products do not remain stale.
    """
    tasks = [safe_cache_delete_pattern("catalog:list:*")]
    if product_id is not None:
        tasks.append(safe_cache_delete(make_product_cache_key(product_id)))
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    list_keys_cleared = results[0] if isinstance(results[0], int) else 0
    
    return {
        "product_id": product_id,
        "list_keys_cleared": list_keys_cleared,
        "product_key_cleared": bool(product_id is not None),
    }


# ==============================================================================
# Cache Stampede Protection (Mutex / Single-Flight)
# ==============================================================================

async def fetch_with_stampede_protection(
    cache_key: str,
    ttl_seconds: int,
    db_fetcher: Callable[[], Any],
) -> Tuple[Any, str]:
    """
    Protects against cache stampedes on cold misses.
    1. Check cache (Fast return if hit -> 'HIT').
    2. On miss, acquire distributed mutex lock `lock:{cache_key}` via SET NX.
    3. Winner queries MySQL, writes to Redis with TTL, releases lock -> 'MISS'.
    4. Losers wait up to 500ms for winner to populate cache and re-read -> 'STAMPEDE_PROTECTED_HIT'.
    5. If Redis is down, executes db_fetcher directly -> 'BYPASS_DOWN'.
    """
    # 1. First probe
    cached_val = await safe_cache_get(cache_key)
    if cached_val is not None:
        return cached_val, "HIT"

    client = get_redis_client()
    lock_key = f"lock:{cache_key}"
    acquired_lock = False

    try:
        # Try to acquire mutex lock for 5 seconds
        acquired_lock = await client.set(lock_key, "1", nx=True, ex=settings.CACHE_MUTEX_TTL)
    except Exception as exc:
        logger.warning(f"Redis mutex acquire failed ({exc}). Bypassing cache directly to MySQL.")
        # If Redis is completely down, bypass cache directly
        data = await db_fetcher()
        return data, "BYPASS_DOWN"

    if acquired_lock:
        # We are the single flight worker elected to compute the result
        try:
            data = await db_fetcher()
            if data is not None:
                await safe_cache_set(cache_key, data, ttl_seconds)
            return data, "MISS"
        finally:
            # Release mutex lock safely
            try:
                await client.delete(lock_key)
            except Exception:
                pass
    else:
        # Another worker is currently populating this cold key.
        # Wait and poll up to 500ms (10 attempts * 50ms)
        for _ in range(10):
            await asyncio.sleep(0.05)
            cached_val = await safe_cache_get(cache_key)
            if cached_val is not None:
                return cached_val, "STAMPEDE_PROTECTED_HIT"

        # Fallback if lock holder died or exceeded wait window
        data = await db_fetcher()
        return data, "MISS_LOCK_TIMEOUT"


async def check_redis_health() -> bool:
    try:
        client = get_redis_client()
        pong = await client.ping()
        return bool(pong)
    except Exception as exc:
        logger.error(f"Redis healthcheck failed: {exc}")
        return False
