from __future__ import annotations

import asyncio
from unittest.mock import patch
import pytest
from httpx import AsyncClient
from app import repository


@pytest.mark.asyncio
async def test_cache_stampede_protection_on_cold_key(client: AsyncClient):
    """
    Simulates high-concurrency cold traffic where 10 concurrent requests arrive
    for the exact same uncached catalog query simultaneously.
    Verifies that the underlying MySQL query is executed only once or bounded,
    with other requests receiving the stampede-protected result.
    """
    url = "/api/v1/products?brand_id=1&page=1&page_size=10"

    real_list_products = repository.list_products
    call_count = 0

    async def counting_list_products(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        # Add slight delay to simulate database query execution time
        await asyncio.sleep(0.08)
        return await real_list_products(*args, **kwargs)

    with patch("app.repository.list_products", side_effect=counting_list_products):
        # Fire 10 concurrent requests simultaneously
        tasks = [client.get(url) for _ in range(10)]
        responses = await asyncio.gather(*tasks)

    # All 10 requests must succeed with HTTP 200
    for r in responses:
        assert r.status_code == 200
        assert len(r.json()["items"]) > 0

    # Inspect cache statuses
    statuses = [r.headers.get("X-Cache-Status") for r in responses]
    assert "MISS" in statuses

    # Without stampede protection, call_count would be 10.
    # With stampede protection, only 1 (or at most 2 under tight race) queries MySQL.
    assert call_count <= 2, f"Expected stampede protection to restrict DB calls to <=2, but observed {call_count} calls."


@pytest.mark.asyncio
async def test_mutex_lock_ownership_prevents_unauthorized_release():
    """
    Verifies that releasing a mutex lock requires the exact token that acquired it.
    If a worker's lock expired and was re-acquired by another worker, the former worker
    must not delete the new owner's lock.
    """
    from app.cache import get_redis_client, RELEASE_LOCK_LUA

    redis = get_redis_client()
    lock_key = "lock:test_ownership_key"
    token_a = "token_owner_a"
    token_b = "token_owner_b"

    # Worker A acquires lock
    acquired = await redis.set(lock_key, token_a, nx=True, ex=10)
    assert acquired is True

    # Worker B tries to release Worker A's lock using wrong token -> must return 0 and not delete lock
    res = await redis.eval(RELEASE_LOCK_LUA, 1, lock_key, token_b)
    assert res == 0
    assert await redis.get(lock_key) == token_a

    # Worker A releases using correct token -> must return 1 and delete lock
    res_correct = await redis.eval(RELEASE_LOCK_LUA, 1, lock_key, token_a)
    assert res_correct == 1
    assert await redis.get(lock_key) is None
