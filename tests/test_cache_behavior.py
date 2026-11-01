from __future__ import annotations

import uuid
import pytest
from httpx import AsyncClient
from app.cache import get_redis_client, make_list_cache_key, make_product_cache_key


@pytest.mark.asyncio
async def test_cold_and_warm_cache_transitions(client: AsyncClient):
    redis = get_redis_client()
    url = "/api/v1/products?category_id=4&page=1&page_size=10"

    # Request 1 (Cold Cache)
    res1 = await client.get(url)
    assert res1.status_code == 200
    assert res1.headers.get("X-Cache-Status") == "MISS"
    data1 = res1.json()

    # Request 2 (Warm Cache)
    res2 = await client.get(url)
    assert res2.status_code == 200
    assert res2.headers.get("X-Cache-Status") == "HIT"
    data2 = res2.json()

    # Ensure payload consistency
    assert data1["items"] == data2["items"]
    assert data1["pagination"] == data2["pagination"]


@pytest.mark.asyncio
async def test_cache_invalidation_on_product_update(client: AsyncClient, admin_headers: dict):
    # 1. Warm single product cache
    prod_id = 1
    res_cold = await client.get(f"/api/v1/products/{prod_id}")
    assert res_cold.status_code == 200
    assert res_cold.headers.get("X-Cache-Status") == "MISS"
    original_title = res_cold.json()["title"]

    res_warm = await client.get(f"/api/v1/products/{prod_id}")
    assert res_warm.headers.get("X-Cache-Status") == "HIT"

    # Also warm list cache
    list_url = "/api/v1/products?page=1&page_size=20"
    res_list1 = await client.get(list_url)
    assert res_list1.headers.get("X-Cache-Status") == "MISS"
    res_list2 = await client.get(list_url)
    assert res_list2.headers.get("X-Cache-Status") == "HIT"

    # 2. Mutate product
    new_title = f"Updated Title {uuid.uuid4().hex[:6]}"
    patch_res = await client.patch(
        f"/api/v1/products/{prod_id}",
        json={"title": new_title},
        headers=admin_headers,
    )
    assert patch_res.status_code == 200

    # 3. Verify single product cache was invalidated (Subsequent GET must be MISS with new title)
    res_after_update = await client.get(f"/api/v1/products/{prod_id}")
    assert res_after_update.status_code == 200
    assert res_after_update.headers.get("X-Cache-Status") == "MISS"
    assert res_after_update.json()["title"] == new_title

    # 4. Verify list cache was also invalidated
    res_list_after = await client.get(list_url)
    assert res_list_after.status_code == 200
    assert res_list_after.headers.get("X-Cache-Status") == "MISS"


@pytest.mark.asyncio
async def test_cache_invalidation_on_product_deletion(client: AsyncClient, admin_headers: dict):
    # Create product to delete
    create_res = await client.post(
        "/api/v1/products",
        json={
            "sku": f"SKU-DEL-{uuid.uuid4().hex[:6]}",
            "title": "Item To Delete",
            "slug": f"item-to-delete-{uuid.uuid4().hex[:6]}",
            "price": 1200.00,
            "category_id": 4,
            "brand_id": 1,
            "stock_quantity": 5,
        },
        headers=admin_headers,
    )
    prod_id = create_res.json()["id"]

    # Warm cache
    await client.get(f"/api/v1/products/{prod_id}")
    warm_res = await client.get(f"/api/v1/products/{prod_id}")
    assert warm_res.headers.get("X-Cache-Status") == "HIT"

    # Delete product
    del_res = await client.delete(f"/api/v1/products/{prod_id}", headers=admin_headers)
    assert del_res.status_code == 204

    # Subsequent GET must return 404 and must NOT return stale cached data
    after_del = await client.get(f"/api/v1/products/{prod_id}")
    assert after_del.status_code == 404


def test_make_list_cache_key_full_sha256_entropy():
    """
    Verifies that canonical list keys use full 64-character SHA-256 digests
    and generate distinct keys for different filters or pagination bounds.
    """
    params_a = {"min_price": 1000, "max_price": 5000, "page": 1, "page_size": 10}
    params_b = {"min_price": 5000, "max_price": 10000, "page": 1, "page_size": 10}
    params_c = {"min_price": 1000, "max_price": 5000, "page": 2, "page_size": 10}

    key_a = make_list_cache_key(params_a)
    key_b = make_list_cache_key(params_b)
    key_c = make_list_cache_key(params_c)

    assert len({key_a, key_b, key_c}) == 3
    # Verify full SHA-256 (64 hex characters) is used
    hash_part = key_a.replace("catalog:list:", "")
    assert len(hash_part) == 64


@pytest.mark.asyncio
async def test_zero_cache_key_collision_across_distinct_filters(client: AsyncClient):
    # Filter A: min_price=1000, max_price=5000, page=1
    params_a = {"min_price": 1000, "max_price": 5000, "page": 1, "page_size": 10}
    # Filter B: min_price=5000, max_price=10000, page=1
    params_b = {"min_price": 5000, "max_price": 10000, "page": 1, "page_size": 10}
    # Filter C: min_price=1000, max_price=5000, page=2
    params_c = {"min_price": 1000, "max_price": 5000, "page": 2, "page_size": 10}

    key_a = make_list_cache_key(params_a)
    key_b = make_list_cache_key(params_b)
    key_c = make_list_cache_key(params_c)

    # All cache keys must be distinct
    assert len({key_a, key_b, key_c}) == 3

    # Warm all 3 in Redis
    res_a = await client.get("/api/v1/products?min_price=1000&max_price=5000&page=1&page_size=10")
    res_b = await client.get("/api/v1/products?min_price=5000&max_price=10000&page=1&page_size=10")
    res_c = await client.get("/api/v1/products?min_price=1000&max_price=5000&page=2&page_size=10")

    # Second requests hit cache with respective correct datasets
    res_a_hit = await client.get("/api/v1/products?min_price=1000&max_price=5000&page=1&page_size=10")
    res_b_hit = await client.get("/api/v1/products?min_price=5000&max_price=10000&page=1&page_size=10")
    res_c_hit = await client.get("/api/v1/products?min_price=1000&max_price=5000&page=2&page_size=10")

    assert res_a_hit.headers.get("X-Cache-Status") == "HIT"
    assert res_b_hit.headers.get("X-Cache-Status") == "HIT"
    assert res_c_hit.headers.get("X-Cache-Status") == "HIT"

    # Results must reflect their specific queries, not colliding
    items_a = [p["id"] for p in res_a_hit.json()["items"]]
    items_b = [p["id"] for p in res_b_hit.json()["items"]]
    items_c = [p["id"] for p in res_c_hit.json()["items"]]

    assert set(items_a).isdisjoint(set(items_b))
    assert set(items_a).isdisjoint(set(items_c))
