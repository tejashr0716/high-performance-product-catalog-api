from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class CategoryBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    slug: str = Field(..., min_length=2, max_length=120)
    parent_id: Optional[int] = None


class CategoryResponse(CategoryBase):
    id: int
    created_at: Optional[datetime] = None
    subcategories: List[CategoryResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class BrandBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    slug: str = Field(..., min_length=2, max_length=120)
    country: Optional[str] = "India"


class BrandResponse(BrandBase):
    id: int
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ProductBase(BaseModel):
    sku: str = Field(..., min_length=3, max_length=64, description="Unique stock keeping unit code")
    title: str = Field(..., min_length=3, max_length=255)
    slug: str = Field(..., min_length=3, max_length=255)
    description: Optional[str] = None
    price: Decimal = Field(..., gt=0, decimal_places=2, description="Price in INR")
    currency: str = Field(default="INR", max_length=3)
    stock_quantity: int = Field(default=0, ge=0)
    category_id: int = Field(..., gt=0)
    brand_id: int = Field(..., gt=0)
    rating: Decimal = Field(default=Decimal("0.00"), ge=0, le=5, decimal_places=2)
    is_active: bool = True

    @field_validator("sku", "title", "slug")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("Field cannot be empty or whitespace only.")
        return s


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=3, max_length=255)
    description: Optional[str] = None
    price: Optional[Decimal] = Field(None, gt=0, decimal_places=2)
    stock_quantity: Optional[int] = Field(None, ge=0)
    category_id: Optional[int] = Field(None, gt=0)
    brand_id: Optional[int] = Field(None, gt=0)
    rating: Optional[Decimal] = Field(None, ge=0, le=5, decimal_places=2)
    is_active: Optional[bool] = None


class ProductResponse(ProductBase):
    id: int
    version: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    category_name: Optional[str] = None
    brand_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ProductFilterParams(BaseModel):
    q: Optional[str] = Field(None, max_length=100, description="Search term against title and description")
    category_id: Optional[int] = Field(None, gt=0, description="Category filter (includes child categories recursively)")
    brand_id: Optional[int] = Field(None, gt=0, description="Brand filter")
    min_price: Optional[Decimal] = Field(None, ge=0, description="Minimum price bound")
    max_price: Optional[Decimal] = Field(None, ge=0, description="Maximum price bound")
    in_stock: Optional[bool] = Field(None, description="Filter for products with stock_quantity > 0")
    sort_by: Literal["id", "price", "rating", "created_at", "title"] = "id"
    sort_dir: Literal["asc", "desc"] = "desc"
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class PaginationMeta(BaseModel):
    page: int
    page_size: int
    total_items: int
    total_pages: int
    has_next: bool
    has_prev: bool


class PaginatedProductResponse(BaseModel):
    items: List[ProductResponse]
    pagination: PaginationMeta
    cache_status: str = Field(default="MISS", description="HIT, MISS, STAMPEDE_PROTECTED_HIT, or BYPASS_DOWN")


class HealthResponse(BaseModel):
    status: str
    service: str
    mysql_connected: bool
    redis_connected: bool
    timestamp: str
