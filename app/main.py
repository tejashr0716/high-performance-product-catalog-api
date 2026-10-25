from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import math
import time
from typing import Any, Dict, List, Optional
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import repository
from app.cache import (
    check_redis_health,
    close_redis,
    fetch_with_stampede_protection,
    get_redis_client,
    invalidate_product_cache,
    make_list_cache_key,
    make_product_cache_key,
    safe_cache_get,
    safe_cache_set,
)
from app.config import settings
from app.db import check_db_health, close_db_pool, init_db_pool
from app.schemas import (
    BrandResponse,
    CategoryResponse,
    HealthResponse,
    PaginatedProductResponse,
    PaginationMeta,
    ProductCreate,
    ProductFilterParams,
    ProductResponse,
    ProductUpdate,
)
from app.security import verify_admin_api_key


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize database pool & redis
    await init_db_pool()
    get_redis_client()
    yield
    # Shutdown: clean release of connections
    await close_db_pool()
    await close_redis()


app = FastAPI(
    title="High-Performance Product Catalog API",
    description="Production-grade e-commerce catalog API with MySQL 8, Redis caching, stampede protection, and hierarchical filtering.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files mount
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.middleware("http")
async def add_timing_header(request: Request, call_next):
    start_time = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - start_time) * 1000.0, 3)
    response.headers["X-Process-Time-Ms"] = str(duration_ms)
    return response


# ==============================================================================
# UI & Health Endpoints
# ==============================================================================

@app.get("/", include_in_schema=False)
async def serve_dashboard():
    return FileResponse("static/index.html")


@app.get("/health", response_model=HealthResponse, tags=["Observability"])
async def health_check():
    mysql_ok = await check_db_health()
    redis_ok = await check_redis_health()
    overall = "HEALTHY" if (mysql_ok and redis_ok) else ("DEGRADED" if mysql_ok else "UNHEALTHY")

    return HealthResponse(
        status=overall,
        service=settings.SERVICE_NAME,
        mysql_connected=mysql_ok,
        redis_connected=redis_ok,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


# ==============================================================================
# Catalog Listing & Search (Cached with Stampede Protection)
# ==============================================================================

@app.get(
    "/api/v1/products",
    response_model=PaginatedProductResponse,
    tags=["Catalog"],
    summary="List and filter catalog products with caching and stampede protection",
)
async def list_products(
    response: Response,
    q: Optional[str] = Query(None, description="Search term against title or description"),
    category_id: Optional[int] = Query(None, gt=0, description="Category filter (includes child categories)"),
    brand_id: Optional[int] = Query(None, gt=0, description="Brand filter"),
    min_price: Optional[float] = Query(None, ge=0, description="Minimum price bound"),
    max_price: Optional[float] = Query(None, ge=0, description="Maximum price bound"),
    in_stock: Optional[bool] = Query(None, description="Filter in-stock items only"),
    sort_by: str = Query("id", pattern="^(id|price|rating|created_at|title)$"),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    bypass_cache: bool = Query(False, description="Forces primary MySQL query for uncached benchmarking"),
):
    filters = ProductFilterParams(
        q=q,
        category_id=category_id,
        brand_id=brand_id,
        min_price=min_price,
        max_price=max_price,
        in_stock=in_stock,
        sort_by=sort_by,
        sort_dir=sort_dir,
        page=page,
        page_size=page_size,
    )

    async def fetch_from_db():
        rows, total = await repository.list_products(filters)
        total_pages = math.ceil(total / filters.page_size) if total > 0 else 0
        return {
            "items": rows,
            "total_items": total,
            "total_pages": total_pages,
            "page": filters.page,
            "page_size": filters.page_size,
            "has_next": filters.page < total_pages,
            "has_prev": filters.page > 1,
        }

    if bypass_cache:
        payload = await fetch_from_db()
        cache_status = "BYPASS"
    else:
        cache_key = make_list_cache_key(filters.model_dump(mode="json"))
        payload, cache_status = await fetch_with_stampede_protection(
            cache_key=cache_key,
            ttl_seconds=settings.CACHE_TTL_LIST,
            db_fetcher=fetch_from_db,
        )

    response.headers["X-Cache-Status"] = cache_status

    pagination_meta = PaginationMeta(
        page=payload["page"],
        page_size=payload["page_size"],
        total_items=payload["total_items"],
        total_pages=payload["total_pages"],
        has_next=payload["has_next"],
        has_prev=payload["has_prev"],
    )

    return PaginatedProductResponse(
        items=payload["items"],
        pagination=pagination_meta,
        cache_status=cache_status,
    )


# ==============================================================================
# Single Product Detail (Cached with Automatic Invalidation)
# ==============================================================================

@app.get(
    "/api/v1/products/{product_id}",
    response_model=ProductResponse,
    tags=["Catalog"],
    summary="Get single product details by ID",
)
async def get_product(product_id: int, response: Response, bypass_cache: bool = False):
    async def fetch_from_db():
        return await repository.get_product_by_id(product_id)

    if bypass_cache:
        product = await fetch_from_db()
        cache_status = "BYPASS"
    else:
        cache_key = make_product_cache_key(product_id)
        product, cache_status = await fetch_with_stampede_protection(
            cache_key=cache_key,
            ttl_seconds=settings.CACHE_TTL_PRODUCT,
            db_fetcher=fetch_from_db,
        )

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with ID {product_id} not found",
        )

    response.headers["X-Cache-Status"] = cache_status
    return product


# ==============================================================================
# Protected Write Operations (Admin Key Required)
# ==============================================================================

@app.post(
    "/api/v1/products",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Admin Product Management"],
    summary="Create a new catalog product (Protected)",
)
async def create_product(
    product_in: ProductCreate,
    _: bool = Depends(verify_admin_api_key),
):
    try:
        created = await repository.create_product(product_in)
        # Purge list caches so new product immediately appears in search/listings
        await invalidate_product_cache()
        return created
    except Exception as exc:
        if "Duplicate entry" in str(exc):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Product with SKU '{product_in.sku}' or slug '{product_in.slug}' already exists.",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create product: {str(exc)}",
        )


@app.patch(
    "/api/v1/products/{product_id}",
    response_model=ProductResponse,
    tags=["Admin Product Management"],
    summary="Update existing product (Protected)",
)
async def update_product(
    product_id: int,
    updates: ProductUpdate,
    _: bool = Depends(verify_admin_api_key),
):
    updated = await repository.update_product(product_id, updates)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with ID {product_id} not found",
        )

    # Invalidate both the individual product cache and all paginated lists
    await invalidate_product_cache(product_id=product_id)
    return updated


@app.delete(
    "/api/v1/products/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Admin Product Management"],
    summary="Soft-delete / Archive product (Protected)",
)
async def delete_product(
    product_id: int,
    _: bool = Depends(verify_admin_api_key),
):
    deleted = await repository.delete_product(product_id, soft=True)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with ID {product_id} not found",
        )

    # Invalidate product cache and lists immediately
    await invalidate_product_cache(product_id=product_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ==============================================================================
# Metadata Endpoints (Categories & Brands)
# ==============================================================================

@app.get("/api/v1/categories", response_model=List[Dict[str, Any]], tags=["Metadata"])
async def list_categories():
    cache_key = "catalog:categories:all"
    cached = await safe_cache_get(cache_key)
    if cached is not None:
        return cached

    categories = await repository.get_all_categories()
    await safe_cache_set(cache_key, categories, ttl_seconds=settings.CACHE_TTL_METADATA)
    return categories


@app.get("/api/v1/brands", response_model=List[Dict[str, Any]], tags=["Metadata"])
async def list_brands():
    cache_key = "catalog:brands:all"
    cached = await safe_cache_get(cache_key)
    if cached is not None:
        return cached

    brands = await repository.get_all_brands()
    await safe_cache_set(cache_key, brands, ttl_seconds=settings.CACHE_TTL_METADATA)
    return brands


@app.post("/api/v1/admin/cache/purge", tags=["Admin Product Management"])
async def purge_cache(_: bool = Depends(verify_admin_api_key)):
    """Manually purges all catalog Redis keys."""
    res = await invalidate_product_cache()
    return {"status": "PURGED", "details": res}
