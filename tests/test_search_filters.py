from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_recursive_category_hierarchy_filtering(client: AsyncClient):
    # Root Category 1: Electronics (id=1) has child categories (Audio=4, Laptops=5, Smartphones=6, Cameras=7)
    # Querying root category_id=1 must return items from child categories
    res = await client.get("/api/v1/products?category_id=1&page_size=50")
    assert res.status_code == 200
    data = res.json()
    items = data["items"]
    assert len(items) > 0

    # Ensure returned items belong to descendants of Electronics
    for item in items:
        assert item["category_id"] in [4, 5, 6, 7]


@pytest.mark.asyncio
async def test_brand_filtering(client: AsyncClient):
    # Filter by Brand 1 (Sony)
    res = await client.get("/api/v1/products?brand_id=1&page_size=25")
    assert res.status_code == 200
    data = res.json()
    for item in data["items"]:
        assert item["brand_id"] == 1
        assert item["brand_name"] == "Sony"


@pytest.mark.asyncio
async def test_price_range_filtering(client: AsyncClient):
    min_p = 5000.00
    max_p = 15000.00
    res = await client.get(f"/api/v1/products?min_price={min_p}&max_price={max_p}&page_size=30")
    assert res.status_code == 200
    data = res.json()
    assert len(data["items"]) > 0
    for item in data["items"]:
        price = float(item["price"])
        assert min_p <= price <= max_p


@pytest.mark.asyncio
async def test_in_stock_filtering(client: AsyncClient):
    res = await client.get("/api/v1/products?in_stock=true&page_size=30")
    assert res.status_code == 200
    data = res.json()
    for item in data["items"]:
        assert item["stock_quantity"] > 0


@pytest.mark.asyncio
async def test_keyword_search_across_title_and_description(client: AsyncClient):
    res = await client.get("/api/v1/products?q=Headphones&page_size=20")
    assert res.status_code == 200
    data = res.json()
    assert len(data["items"]) > 0
    for item in data["items"]:
        text = (item["title"] + " " + (item["description"] or "")).lower()
        assert "headphone" in text


@pytest.mark.asyncio
async def test_sorting_orders(client: AsyncClient):
    # Price ASC
    res_asc = await client.get("/api/v1/products?sort_by=price&sort_dir=asc&page_size=20")
    assert res_asc.status_code == 200
    prices_asc = [float(p["price"]) for p in res_asc.json()["items"]]
    assert prices_asc == sorted(prices_asc)

    # Price DESC
    res_desc = await client.get("/api/v1/products?sort_by=price&sort_dir=desc&page_size=20")
    assert res_desc.status_code == 200
    prices_desc = [float(p["price"]) for p in res_desc.json()["items"]]
    assert prices_desc == sorted(prices_desc, reverse=True)


@pytest.mark.asyncio
async def test_stable_pagination_slices(client: AsyncClient):
    # Page 1
    res1 = await client.get("/api/v1/products?page=1&page_size=15&sort_by=id&sort_dir=asc")
    assert res1.status_code == 200
    data1 = res1.json()
    ids_page1 = [p["id"] for p in data1["items"]]
    assert len(ids_page1) == 15

    # Page 2
    res2 = await client.get("/api/v1/products?page=2&page_size=15&sort_by=id&sort_dir=asc")
    assert res2.status_code == 200
    data2 = res2.json()
    ids_page2 = [p["id"] for p in data2["items"]]
    assert len(ids_page2) == 15

    # Slices must be completely disjoint (no duplicate records between pages)
    assert set(ids_page1).isdisjoint(set(ids_page2))
    assert max(ids_page1) < min(ids_page2)


@pytest.mark.asyncio
async def test_sql_parameterization_injection_safety(client: AsyncClient):
    # SQL injection attack strings must be handled as inert string literals without syntax errors
    malicious_inputs = [
        "' OR '1'='1",
        "'; DROP TABLE products; --",
        "1 UNION SELECT 1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16",
    ]
    for attack in malicious_inputs:
        res = await client.get(f"/api/v1/products?q={attack}")
        assert res.status_code == 200
        # Returns 0 results or matches literal text, without dropping tables or breaking SQL
        assert isinstance(res.json()["items"], list)
