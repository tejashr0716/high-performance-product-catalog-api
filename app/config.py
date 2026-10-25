from __future__ import annotations

import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # MySQL Configuration
    DB_HOST: str = "127.0.0.1"
    DB_PORT: int = 3307
    DB_USER: str = "root"
    DB_PASSWORD: str = ""
    DB_NAME: str = "catalog_db"
    DB_SOCKET: Optional[str] = "/tmp/mysql3307.sock"
    DB_POOL_MIN_SIZE: int = 5
    DB_POOL_MAX_SIZE: int = 25

    # Redis Configuration
    REDIS_HOST: str = "127.0.0.1"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: Optional[str] = None
    REDIS_TIMEOUT_SECONDS: float = 1.0

    # Cache TTLs (Seconds)
    CACHE_TTL_PRODUCT: int = 3600    # 1 hour for individual product details
    CACHE_TTL_LIST: int = 300        # 5 minutes for search / category listings
    CACHE_TTL_METADATA: int = 86400  # 24 hours for brands and category trees

    # Cache Stampede Mutex TTL (Seconds)
    CACHE_MUTEX_TTL: int = 5         # Max time to hold single-flight lock during cold population

    # Admin Security
    ADMIN_API_KEY: str = "catalog-admin-secret-key-at-least-32-chars-long"

    # Service
    SERVICE_NAME: str = "high-performance-product-catalog-api"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False


settings = Settings()
