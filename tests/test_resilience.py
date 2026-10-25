from __future__ import annotations

from unittest.mock import AsyncMock, patch
import pytest
from httpx import AsyncClient
import redis.exceptions


@pytest.mark.asyncio
async def test_redis_failure_graceful_fallback(client: AsyncClient):
    """
    Simulates a Redis outage or network partition during read operations.
    Verifies that the API never fails with HTTP 500, instead falling back
    gracefully to MySQL and delivering legitimate catalog data.
    """
    # Mock Redis client get/set to simulate connection failure
    with patch("app.cache.get_redis_client") as mock_client_factory:
        mock_redis = AsyncMock()
        mock_redis.get.side_effect = redis.exceptions.ConnectionError("Redis connection refused on 6379")
        mock_redis.set.side_effect = redis.exceptions.ConnectionError("Redis connection refused on 6379")
        mock_client_factory.return_value = mock_redis

        # Query catalog
        res = await client.get("/api/v1/products?page=1&page_size=10")
        assert res.status_code == 200
        data = res.json()
        assert len(data["items"]) == 10
        # Headers should indicate bypass/down mode
        assert res.headers.get("X-Cache-Status") in ["BYPASS_DOWN", "BYPASS"]


@pytest.mark.asyncio
async def test_health_check_reflects_redis_degradation(client: AsyncClient):
    """
    Verifies that /health accurately reports service degradation when Redis is down.
    """
    with patch("app.main.check_redis_health", return_value=False):
        res = await client.get("/health")
        assert res.status_code == 200
        health = res.json()
        assert health["status"] == "DEGRADED"
        assert health["mysql_connected"] is True
        assert health["redis_connected"] is False
