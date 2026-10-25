from __future__ import annotations

import uuid
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_read_product_by_id(client: AsyncClient):
    res = await client.get("/api/v1/products/1")
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == 1
    assert "sku" in data
    assert "price" in data
    assert "category_name" in data


@pytest.mark.asyncio
async def test_read_nonexistent_product_returns_404(client: AsyncClient):
    res = await client.get("/api/v1/products/999999")
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_unauthorized_product_creation_rejected(client: AsyncClient):
    payload = {
        "sku": f"SKU-UNAUTH-{uuid.uuid4().hex[:6]}",
        "title": "Unauthorized Widget",
        "slug": f"unauthorized-widget-{uuid.uuid4().hex[:6]}",
        "price": 999.00,
        "category_id": 1,
        "brand_id": 1,
        "stock_quantity": 10,
    }
    # No header
    res = await client.post("/api/v1/products", json=payload)
    assert res.status_code == 401

    # Invalid header
    res_bad = await client.post("/api/v1/products", json=payload, headers={"X-Admin-Key": "wrong-key"})
    assert res_bad.status_code == 403


@pytest.mark.asyncio
async def test_authorized_product_crud_lifecycle(client: AsyncClient, admin_headers: dict):
    unique_suffix = uuid.uuid4().hex[:8]
    create_payload = {
        "sku": f"SKU-TEST-{unique_suffix}",
        "title": "Pro Noise Cancelling Wireless Headphones",
        "slug": f"pro-nc-wireless-headphones-{unique_suffix}",
        "description": "High-fidelity studio headphones with active cancellation.",
        "price": 14999.50,
        "currency": "INR",
        "stock_quantity": 45,
        "category_id": 4,  # Audio & Headphones
        "brand_id": 1,     # Sony
        "rating": 4.85,
        "is_active": True,
    }

    # 1. Create Product
    create_res = await client.post("/api/v1/products", json=create_payload, headers=admin_headers)
    assert create_res.status_code == 201
    created_data = create_res.json()
    prod_id = created_data["id"]
    assert created_data["sku"] == create_payload["sku"]
    assert float(created_data["price"]) == 14999.50
    assert created_data["version"] == 1

    # 2. Read Product
    read_res = await client.get(f"/api/v1/products/{prod_id}")
    assert read_res.status_code == 200
    assert read_res.json()["title"] == create_payload["title"]

    # 3. Update Product (Optimistic Versioning)
    update_payload = {
        "title": "Pro Noise Cancelling Headphones - Gen 2",
        "price": 13999.00,
        "stock_quantity": 100,
    }
    update_res = await client.patch(f"/api/v1/products/{prod_id}", json=update_payload, headers=admin_headers)
    assert update_res.status_code == 200
    updated_data = update_res.json()
    assert updated_data["title"] == "Pro Noise Cancelling Headphones - Gen 2"
    assert float(updated_data["price"]) == 13999.00
    assert updated_data["stock_quantity"] == 100
    assert updated_data["version"] == 2  # Version incremented

    # 4. Soft Delete / Archive Product
    delete_res = await client.delete(f"/api/v1/products/{prod_id}", headers=admin_headers)
    assert delete_res.status_code == 204

    # 5. Verify Soft-Archived product does not appear in active listings
    list_res = await client.get(f"/api/v1/products?q={create_payload['sku']}")
    assert list_res.status_code == 200
    assert list_res.json()["pagination"]["total_items"] == 0


@pytest.mark.asyncio
async def test_duplicate_sku_rejection(client: AsyncClient, admin_headers: dict):
    unique = uuid.uuid4().hex[:6]
    payload = {
        "sku": f"SKU-DUP-{unique}",
        "title": "Original Item",
        "slug": f"original-item-{unique}",
        "price": 500.00,
        "category_id": 4,
        "brand_id": 1,
    }

    res1 = await client.post("/api/v1/products", json=payload, headers=admin_headers)
    assert res1.status_code == 201

    # Attempt to insert same SKU
    payload_dup = dict(payload)
    payload_dup["slug"] = f"different-slug-{unique}"
    res2 = await client.post("/api/v1/products", json=payload_dup, headers=admin_headers)
    assert res2.status_code == 409
    assert "already exists" in res2.json()["detail"].lower()
