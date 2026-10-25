from __future__ import annotations

import asyncio
import os
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Ensure environment uses test database and local ports
os.environ["DB_PORT"] = "3307"
os.environ["DB_NAME"] = "catalog_db"
os.environ["DB_SOCKET"] = "/tmp/mysql3307.sock"
os.environ["REDIS_PORT"] = "6379"

from app.cache import close_redis, get_redis_client, safe_cache_delete_pattern
from app.config import settings
from app.db import close_db_pool, init_db_pool
from app.main import app


@pytest_asyncio.fixture(scope="function")
async def client():
    await init_db_pool()
    get_redis_client()
    await safe_cache_delete_pattern("catalog:*")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    await safe_cache_delete_pattern("catalog:*")
    await close_db_pool()
    await close_redis()


@pytest.fixture
def admin_headers():
    return {"X-Admin-Key": settings.ADMIN_API_KEY}
