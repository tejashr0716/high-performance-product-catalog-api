from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple
from app.db import execute_query, execute_query_one, execute_write
from app.schemas import ProductCreate, ProductFilterParams, ProductUpdate


async def get_descendant_category_ids(root_category_id: int) -> List[int]:
    """
    Resolves a category and all its hierarchical child categories using
    an ANSI SQL-standard Common Table Expression (WITH RECURSIVE).
    """
    cte_query = """
        WITH RECURSIVE cat_tree AS (
            SELECT id FROM categories WHERE id = %s
            UNION ALL
            SELECT c.id FROM categories c
            INNER JOIN cat_tree ct ON c.parent_id = ct.id
        )
        SELECT id FROM cat_tree;
    """
    rows = await execute_query(cte_query, (root_category_id,))
    return [r["id"] for r in rows]


async def list_products(filters: ProductFilterParams) -> Tuple[List[Dict[str, Any]], int]:
    """
    Executes a high-performance, strictly parameterized search and filtering query.
    Utilizes composite MySQL indexes and escapes all user parameters.
    """
    where_clauses = ["p.is_active = TRUE"]
    params: List[Any] = []

    # 1. Recursive Category Filter
    if filters.category_id:
        category_ids = await get_descendant_category_ids(filters.category_id)
        if category_ids:
            format_strings = ",".join(["%s"] * len(category_ids))
            where_clauses.append(f"p.category_id IN ({format_strings})")
            params.extend(category_ids)
        else:
            where_clauses.append("p.category_id = %s")
            params.append(filters.category_id)

    # 2. Brand Filter
    if filters.brand_id:
        where_clauses.append("p.brand_id = %s")
        params.append(filters.brand_id)

    # 3. Price Bounds
    if filters.min_price is not None:
        where_clauses.append("p.price >= %s")
        params.append(float(filters.min_price))
    if filters.max_price is not None:
        where_clauses.append("p.price <= %s")
        params.append(float(filters.max_price))

    # 4. Stock Availability Filter
    if filters.in_stock is True:
        where_clauses.append("p.stock_quantity > 0")

    # 5. Search Text Filter (Title and Description)
    if filters.q and filters.q.strip():
        search_kw = f"%{filters.q.strip()}%"
        where_clauses.append("(p.title LIKE %s OR p.description LIKE %s)")
        params.extend([search_kw, search_kw])

    where_sql = " AND ".join(where_clauses)

    # Count Query for accurate pagination metadata
    count_sql = f"SELECT COUNT(*) as total FROM products p WHERE {where_sql}"
    count_row = await execute_query_one(count_sql, tuple(params))
    total_items = count_row["total"] if count_row else 0

    if total_items == 0:
        return [], 0

    # Sorting (Strictly allowlisted)
    allowed_sort_fields = {
        "id": "p.id",
        "price": "p.price",
        "rating": "p.rating",
        "created_at": "p.created_at",
        "title": "p.title",
    }
    sort_column = allowed_sort_fields.get(filters.sort_by, "p.id")
    sort_direction = "DESC" if filters.sort_dir.lower() == "desc" else "ASC"

    # Pagination calculation
    offset = (filters.page - 1) * filters.page_size
    fetch_params = list(params)
    fetch_params.extend([filters.page_size, offset])

    # Data Query with joined Category and Brand metadata
    select_sql = f"""
        SELECT 
            p.id, p.sku, p.title, p.slug, p.description, p.price, p.currency,
            p.stock_quantity, p.category_id, p.brand_id, p.rating, p.is_active,
            p.version, p.created_at, p.updated_at,
            c.name as category_name,
            b.name as brand_name
        FROM products p
        LEFT JOIN categories c ON p.category_id = c.id
        LEFT JOIN brands b ON p.brand_id = b.id
        WHERE {where_sql}
        ORDER BY {sort_column} {sort_direction}
        LIMIT %s OFFSET %s
    """

    rows = await execute_query(select_sql, tuple(fetch_params))
    return rows, total_items


async def get_product_by_id(product_id: int, include_inactive: bool = False) -> Optional[Dict[str, Any]]:
    """Fetches a single product by primary key with joined metadata."""
    where_active = "" if include_inactive else " AND p.is_active = TRUE"
    query = f"""
        SELECT 
            p.id, p.sku, p.title, p.slug, p.description, p.price, p.currency,
            p.stock_quantity, p.category_id, p.brand_id, p.rating, p.is_active,
            p.version, p.created_at, p.updated_at,
            c.name as category_name,
            b.name as brand_name
        FROM products p
        LEFT JOIN categories c ON p.category_id = c.id
        LEFT JOIN brands b ON p.brand_id = b.id
        WHERE p.id = %s{where_active}
    """
    return await execute_query_one(query, (product_id,))


async def create_product(data: ProductCreate) -> Dict[str, Any]:
    """Creates a new product with parameterized insert."""
    insert_sql = """
        INSERT INTO products (
            sku, title, slug, description, price, currency,
            stock_quantity, category_id, brand_id, rating, is_active, version
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1)
    """
    params = (
        data.sku,
        data.title,
        data.slug,
        data.description,
        float(data.price),
        data.currency,
        data.stock_quantity,
        data.category_id,
        data.brand_id,
        float(data.rating),
        data.is_active,
    )
    product_id = await execute_write(insert_sql, params)
    created = await get_product_by_id(product_id)
    assert created is not None
    return created


async def update_product(product_id: int, updates: ProductUpdate) -> Optional[Dict[str, Any]]:
    """
    Applies partial product updates with optimistic version incrementing.
    Returns None if the product does not exist.
    """
    existing = await get_product_by_id(product_id, include_inactive=True)
    if not existing:
        return None

    set_clauses = ["version = version + 1"]
    params: List[Any] = []

    update_dict = updates.model_dump(exclude_unset=True)
    if not update_dict:
        return existing

    for key, value in update_dict.items():
        if value is not None:
            if key == "price" or key == "rating":
                params.append(float(value))
            else:
                params.append(value)
            set_clauses.append(f"{key} = %s")

    params.append(product_id)
    update_sql = f"UPDATE products SET {', '.join(set_clauses)} WHERE id = %s"
    await execute_write(update_sql, tuple(params))

    return await get_product_by_id(product_id, include_inactive=True)


async def delete_product(product_id: int, soft: bool = True) -> bool:
    """
    Soft-archives or hard deletes a product.
    Returns True if an existing product was modified/deleted.
    """
    existing = await get_product_by_id(product_id, include_inactive=True)
    if not existing:
        return False

    if soft:
        await execute_write("UPDATE products SET is_active = FALSE WHERE id = %s", (product_id,))
    else:
        await execute_write("DELETE FROM products WHERE id = %s", (product_id,))
    return True


async def get_all_categories() -> List[Dict[str, Any]]:
    """Retrieves all categories with hierarchy."""
    return await execute_query("SELECT id, name, slug, parent_id, created_at FROM categories ORDER BY parent_id ASC, name ASC")


async def get_all_brands() -> List[Dict[str, Any]]:
    """Retrieves all brands."""
    return await execute_query("SELECT id, name, slug, country, created_at FROM brands ORDER BY name ASC")
