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
async def test_concurrent_cold_key_stampede_protection_coalesces_db_calls():
    """
    Simulates high-concurrency cold traffic where 10 concurrent requests arrive
    for the exact same uncached key simultaneously without needing MySQL.
    Verifies that the underlying fetcher is executed at most twice (coalesced),
    with other requests receiving the stampede-protected result.
    """
    from app.cache import fetch_with_stampede_protection, get_redis_client

    redis = get_redis_client()
    cache_key = "test:cold_concurrent_stampede:key"
    lock_key = f"lock:{cache_key}"
    await redis.delete(cache_key, lock_key)

    call_count = 0
    expected_data = {"id": 101, "name": "Coalesced Result"}

    async def counting_fetcher():
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.08)
        return expected_data

    # Fire 10 concurrent requests simultaneously
    tasks = [
        fetch_with_stampede_protection(cache_key, 60, counting_fetcher)
        for _ in range(10)
    ]
    results = await asyncio.gather(*tasks)

    # All 10 requests must succeed with valid data
    for data, status in results:
        assert data == expected_data
        assert status in ("MISS", "STAMPEDE_PROTECTED_HIT")

    # Call count must be bounded to <= 2 (ideal is 1)
    assert call_count <= 2, f"Expected fetcher calls <=2, but observed {call_count}"
    await redis.delete(cache_key, lock_key)


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


@pytest.mark.asyncio
async def test_lock_holder_failure_releases_mutex():
    """
    Verifies that if the elected single-flight worker fails (throws an exception),
    the mutex lock is guaranteed to be deleted in finally, preventing deadlock for subsequent requests.
    """
    from app.cache import fetch_with_stampede_protection, get_redis_client

    redis = get_redis_client()
    cache_key = "test:failure:key"
    lock_key = f"lock:{cache_key}"

    # Clean up prior state
    await redis.delete(cache_key, lock_key)

    async def failing_db_fetcher():
        raise RuntimeError("Primary database connection dropped")

    with pytest.raises(RuntimeError, match="Primary database connection dropped"):
        await fetch_with_stampede_protection(
            cache_key=cache_key,
            ttl_seconds=60,
            db_fetcher=failing_db_fetcher,
        )

    # Mutex lock MUST NOT remain held in Redis
    assert await redis.get(lock_key) is None


@pytest.mark.asyncio
async def test_lock_expiry_allows_new_acquisition():
    """
    Verifies that if a lock holder hangs or takes longer than the TTL,
    the lock expires naturally in Redis, allowing subsequent acquisitions.
    """
    from app.cache import get_redis_client

    redis = get_redis_client()
    lock_key = "test:expiry:key"
    token_1 = "worker_1"
    token_2 = "worker_2"

    await redis.delete(lock_key)

    # Acquire with short 1-second TTL
    acquired_1 = await redis.set(lock_key, token_1, nx=True, ex=1)
    assert acquired_1 is True

    # Immediate second acquisition must fail
    acquired_early = await redis.set(lock_key, token_2, nx=True, ex=1)
    assert acquired_early is None

    # Wait for expiry
    await asyncio.sleep(1.05)

    # Subsequent acquisition must succeed
    acquired_2 = await redis.set(lock_key, token_2, nx=True, ex=1)
    assert acquired_2 is True
    await redis.delete(lock_key)


@pytest.mark.asyncio
async def test_slow_fetch_wait_and_re_read():
    """
    Verifies that a concurrent request waiting on a cold key polls Redis
    and returns 'STAMPEDE_PROTECTED_HIT' once the winning worker finishes.
    """
    from app.cache import fetch_with_stampede_protection, get_redis_client

    redis = get_redis_client()
    cache_key = "test:slow_fetch:key"
    lock_key = f"lock:{cache_key}"
    await redis.delete(cache_key, lock_key)

    expected_payload = {"product_id": 42, "name": "Concurrency Protected Widget"}

    async def slow_winning_fetcher():
        await asyncio.sleep(0.12)
        return expected_payload

    async def waiting_fetcher():
        return {"error": "Should not be called if cache populated"}

    # Launch winner and waiting worker concurrently
    winner_task = asyncio.create_task(
        fetch_with_stampede_protection(cache_key, 60, slow_winning_fetcher)
    )
    # Slight pause to ensure winner acquires lock first
    await asyncio.sleep(0.02)
    waiting_task = asyncio.create_task(
        fetch_with_stampede_protection(cache_key, 60, waiting_fetcher)
    )

    winner_res, winner_status = await winner_task
    waiting_res, waiting_status = await waiting_task

    assert winner_status == "MISS"
    assert winner_res == expected_payload

    assert waiting_status == "STAMPEDE_PROTECTED_HIT"
    assert waiting_res == expected_payload

    await redis.delete(cache_key, lock_key)


@pytest.mark.asyncio
async def test_slow_fetch_timeout_falls_back_to_db():
    """
    Verifies that if a lock holder takes longer than the max wait window (500ms),
    the waiting request safely times out and fetches directly with 'MISS_LOCK_TIMEOUT'.
    """
    from app.cache import fetch_with_stampede_protection, get_redis_client

    redis = get_redis_client()
    cache_key = "test:timeout_fetch:key"
    lock_key = f"lock:{cache_key}"
    await redis.delete(cache_key, lock_key)

    # Pre-acquire the lock with a dummy token to simulate a hung or stalled worker
    await redis.set(lock_key, "hung_worker_token", nx=True, ex=5)

    fallback_payload = {"id": 99, "data": "Fresh Fallback Fetch"}

    async def fallback_fetcher():
        return fallback_payload

    res, status = await fetch_with_stampede_protection(
        cache_key=cache_key,
        ttl_seconds=60,
        db_fetcher=fallback_fetcher,
    )

    assert status == "MISS_LOCK_TIMEOUT"
    assert res == fallback_payload
    await redis.delete(cache_key, lock_key)


@pytest.mark.asyncio
async def test_redis_outage_gracefully_bypasses_cache():
    """
    Verifies that if Redis is down or unreachable during lock acquisition,
    the application logs a warning and gracefully calls db_fetcher directly with 'BYPASS_DOWN'.
    """
    from app.cache import fetch_with_stampede_protection, get_redis_client
    import redis.exceptions

    expected_data = {"status": "mysql_direct_result"}

    async def db_fetcher():
        return expected_data

    client = get_redis_client()
    # Patch client.set to simulate Redis connection error
    with patch.object(client, "set", side_effect=redis.exceptions.ConnectionError("Redis connection refused")):
        res, status = await fetch_with_stampede_protection(
            cache_key="test:outage:key",
            ttl_seconds=60,
            db_fetcher=db_fetcher,
        )

    assert status == "BYPASS_DOWN"
    assert res == expected_data


@pytest.mark.asyncio
async def test_version_gated_cache_prevents_stale_repopulation():
    """
    Verifies that monotonic version-gated caching rejects setting a stale product version
    into Redis when a newer version has already updated the database.
    """
    from app.cache import get_redis_client, safe_cache_set_versioned, safe_cache_get

    redis = get_redis_client()
    cache_key = "catalog:product:test_stale_race:1"
    min_ver_key = "catalog:product:test_stale_race:1:min_version"
    await redis.delete(cache_key, min_ver_key)

    # 1. Database write committed version 3; invalidation sets min_version = 3
    await redis.set(min_ver_key, "3", ex=3600)

    # 2. Delayed read worker arrived with stale version 2 data (read before write)
    stale_payload = {"id": 1, "title": "Stale Widget", "version": 2}
    set_success = await safe_cache_set_versioned(
        key=cache_key,
        value=stale_payload,
        ttl_seconds=3600,
        version=2,
        min_ver_key=min_ver_key,
    )
    # Stale version MUST be rejected by Lua script
    assert set_success is False
    assert await safe_cache_get(cache_key) is None

    # 3. Fresh read worker arrived with version 3 data
    fresh_payload = {"id": 1, "title": "Fresh Widget V3", "version": 3}
    set_fresh = await safe_cache_set_versioned(
        key=cache_key,
        value=fresh_payload,
        ttl_seconds=3600,
        version=3,
        min_ver_key=min_ver_key,
    )
    assert set_fresh is True
    cached_data = await safe_cache_get(cache_key)
    assert cached_data == fresh_payload

    await redis.delete(cache_key, min_ver_key)
