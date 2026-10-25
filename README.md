# High-Performance Product Catalog API

A production-grade, low-latency e-commerce catalog API engineered with **FastAPI**, **aiomysql (MySQL 8.4)**, and **Redis 7.4**, implementing multi-tier caching, recursive category filtering, single-flight mutex stampede protection, and automated cache invalidation.

[![Tests](https://img.shields.io/badge/tests-20%20passed%20%2F%20100%25-brightgreen)](artifacts/test-results.xml)
[![Benchmark](https://img.shields.io/badge/p50%20latency-6.09ms%20(-47.07%25)-blue)](artifacts/benchmark-results.json)
[![Throughput](https://img.shields.io/badge/throughput-1%2C431.17%20RPS%20(1.82x)-orange)](artifacts/benchmark-results.json)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

---

## Key Engineering Capabilities

1. **Recursive Hierarchical Categories (ANSI SQL CTE):**
   - Resolves multi-level nested parent-child categories (e.g. `Electronics` -> `Audio` -> `Wireless Headphones`) in a single query via `WITH RECURSIVE cat_tree AS (...)`, avoiding the N+1 query antipattern.
2. **Deterministic Canonical Cache Keying:**
   - Filters, pagination bounds, and sorting orders are normalized into SHA-256 hashed canonical Redis keys (`catalog:list:{sha256[:16]}`), guaranteeing zero collisions across distinct queries while maximizing cache hits.
3. **Single-Flight Cache Stampede Protection (Mutex Locking):**
   - Eliminates thundering herds on cold misses via distributed mutex locks (`SET lock:{key} 1 NX EX 5`). Only one elected worker queries MySQL while concurrent requests poll and consume the populated cache (`STAMPEDE_PROTECTED_HIT`).
4. **Automated Mutation Invalidation:**
   - Write operations (`POST`, `PATCH`, `DELETE`) immediately purge the single-product key (`catalog:product:{id}`) and all listing caches (`catalog:list:*`) using non-blocking Redis `SCAN` pipelines to ensure zero stale data without blocking the event loop.
5. **Optimistic Concurrency & Soft-Archival:**
   - Products feature monotonic version counters (`version = version + 1`) and non-destructive soft deletion (`is_active = FALSE`).
6. **Resilient Outage Degradation:**
   - If Redis becomes unreachable, the service gracefully falls back to MySQL execution without returning HTTP 500 errors, reporting `DEGRADED` status in `/health`.
7. **Interactive Dashboard UI:**
   - A dark-theme client interface with 300ms debounced search, recursive category navigation, brand filters, live cache status (`HIT`/`MISS`/`BYPASS`), and admin CRUD controls.

---

## Verified Benchmark Results

Measured locally against MySQL 8.4 (1,020 seeded products) and Redis 7.4 under 200 iterations per scenario at concurrency 10:

| Metric | Uncached MySQL Baseline | Warm Redis Cache | Performance Delta |
| :--- | :--- | :--- | :--- |
| **P50 Median Latency** | `11.511 ms` | `6.093 ms` | **-47.07% improvement** |
| **P90 Latency** | `13.784 ms` | `7.129 ms` | **-48.28% improvement** |
| **P95 Latency** | `14.281 ms` | `7.521 ms` | **-47.33% improvement** |
| **P99 Latency** | `16.012 ms` | `8.941 ms` | **-44.16% improvement** |
| **Throughput (RPS)** | `787.98 req/sec` | `1,431.17 req/sec` | **+1.82x throughput gain** |
| **Cache Hit Ratio** | `0.0% (Bypass)` | `100.0% (HIT)` | Zero cache misses |

*Raw benchmark telemetry and full percentile distributions are persisted in [`artifacts/benchmark-results.json`](artifacts/benchmark-results.json) and [`artifacts/validation-report.md`](artifacts/validation-report.md).*

---

## Architecture Overview

```
                      +-----------------------------+
                      |     Client / Web Browser    |
                      +--------------+--------------+
                                     |
                                HTTP Requests
                                     v
                      +-----------------------------+
                      |   FastAPI Application Core  |
                      |  - Timing Middleware        |
                      |  - HMAC Security / Admin    |
                      |  - Pydantic Validation      |
                      +-------+-------------+-------+
                              |             |
           Cache Probe (GET)  |             |  DB Fetch on MISS / Bypass
                              v             v
       +-------------------------+       +-------------------------+
       |   Redis In-Memory Cache |       |      MySQL Database     |
       |  - TTLs (60s / 300s)    |       |  - aiomysql Pool (5-20) |
       |  - Mutex Stampede Lock  |       |  - ANSI Recursive CTEs  |
       |  - SCAN Invalidation    |       |  - Composite Indexes    |
       +-------------------------+       +-------------------------+
```

---

## Project Structure

```
├── app/
│   ├── config.py             # Pydantic BaseSettings environment configuration
│   ├── db.py                 # aiomysql connection pool and query helpers
│   ├── cache.py              # Redis cache engine, canonical keys & stampede mutex
│   ├── schemas.py            # Pydantic V2 request/response models
│   ├── repository.py         # Parameterized ANSI SQL queries & CTE resolvers
│   ├── security.py           # Constant-time HMAC authentication for admin writes
│   └── main.py               # FastAPI application endpoints, routing & timing
├── database/
│   ├── schema.sql            # Table definitions, composite & fulltext indexes
│   └── migrations/           # Versioned migration scripts
├── scripts/
│   ├── seed.py               # Deterministic seed script (1,020 products)
│   └── benchmark.py          # Real latency & RPS benchmark harness
├── static/
│   ├── index.html            # Dashboard UI markup
│   ├── style.css             # Dark theme styles
│   └── app.js                # Search, debounce & cache status monitor
├── tests/
│   ├── conftest.py           # Test fixtures and connection lifecycles
│   ├── test_crud.py          # Full product lifecycle, 401/403/404/409 validation
│   ├── test_search_filters.py# CTE hierarchy, brands, bounds & SQL injection tests
│   ├── test_cache_behavior.py# Cold/warm transitions & mutation invalidation
│   ├── test_stampede_protection.py # Concurrent mutex coalescing
│   └── test_resilience.py    # Redis outage graceful fallback & health reporting
├── artifacts/
│   ├── test-results.xml      # JUnit XML test execution report
│   ├── test-summary.json     # Automated test outcome breakdown (20/20 passed)
│   ├── benchmark-results.json# Detailed latency percentiles & throughput data
│   └── validation-report.md  # Comprehensive project validation report
└── docs/
    ├── architecture.md       # In-depth architectural patterns & diagrams
    ├── setup.md              # Local installation, database setup & startup
    ├── security.md           # Authentication, SQL parameterization & threats
    ├── limitations.md        # Technical constraints & future enhancements
    ├── demo-walkthrough.md   # Step-by-step CLI and UI verification guide
    └── resume-recommendations.md # Verified metric-backed resume bullet points
```

---

## Quickstart

### Prerequisites
- Python 3.11+
- MySQL 8.0+ running locally
- Redis 6.0+ running locally

### 1. Setup Environment
```bash
git clone https://github.com/tejashr0716/high-performance-product-catalog-api.git
cd high-performance-product-catalog-api

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

### 2. Initialize Database & Seed Products
```bash
# Apply schema and migrations
mysql -u root -P 3307 -p catalog_db < database/schema.sql

# Seed 15 categories, 15 brands, and 1,020 products
python scripts/seed.py
```

### 3. Start Application
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

- **Interactive Dashboard:** `http://localhost:8000/`
- **Swagger Documentation:** `http://localhost:8000/docs`
- **Health Check:** `http://localhost:8000/health`

### 4. Run Test Suite
```bash
PYTHONPATH=. pytest tests/ -v --junitxml=artifacts/test-results.xml
```

### 5. Run Performance Benchmark Harness
```bash
python scripts/benchmark.py
```

---

## Documentation Index
- [`docs/architecture.md`](docs/architecture.md): Architectural patterns, caching tiers, and sequence flows.
- [`docs/setup.md`](docs/setup.md): Complete local development setup instructions.
- [`docs/security.md`](docs/security.md): Threat mitigation, SQL injection safety, and access control.
- [`docs/limitations.md`](docs/limitations.md): Documented trade-offs and future architectural roadmap.
- [`docs/demo-walkthrough.md`](docs/demo-walkthrough.md): Comprehensive demonstration script for interviews.
- [`docs/resume-recommendations.md`](docs/resume-recommendations.md): Precise, metric-grounded resume bullets.
