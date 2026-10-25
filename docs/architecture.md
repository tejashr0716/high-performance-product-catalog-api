# Architecture & System Design

**Project:** High-Performance Product Catalog API  
**Maintainer:** Tejas H R (`https://github.com/tejashr0716`)  

---

## 1. System Overview

The High-Performance Product Catalog API is designed to serve high-throughput, low-latency e-commerce search, browsing, and product retrieval requests. It decouples intensive relational database queries from read-heavy catalog traffic by employing an intelligent multi-tier caching architecture with Redis, while preserving transactional integrity and optimistic locking in MySQL.

```
                      +-----------------------------+
                      |       Client / Browser      |
                      +--------------+--------------+
                                     |
                                     v
                      +-----------------------------+
                      |   FastAPI Application Core  |
                      |  - Request Validation       |
                      |  - Latency Header (Timing)  |
                      |  - Constant-Time HMAC Auth  |
                      +-------+-------------+-------+
                              |             |
                     (Cache)  |             | (Fallback / Miss)
                              v             v
       +-------------------------+       +-------------------------+
       |   Redis In-Memory Cache |       |      MySQL Primary      |
       |  - Key: catalog:list:*  |       |  - aiomysql Pool        |
       |  - Key: catalog:prod:*  |       |  - ANSI Recursive CTEs  |
       |  - Mutex Stampede Lock  |       |  - Composite Indexes    |
       |  - Non-blocking SCAN    |       |  - Optimistic Locks     |
       +-------------------------+       +-------------------------+
```

---

## 2. Key Architectural Patterns

### A. Recursive Category Hierarchy Resolution (ANSI SQL CTE)
E-commerce categories form trees (e.g. `Root -> Electronics -> Audio -> Headphones`). Rather than traversing the tree via repeated queries (N+1 query problem) or flattening hierarchies into denormalized strings:
- The system executes an ANSI SQL Common Table Expression (`WITH RECURSIVE`):
```sql
WITH RECURSIVE cat_tree AS (
    SELECT id FROM categories WHERE id = %s
    UNION ALL
    SELECT c.id FROM categories c
    INNER JOIN cat_tree ct ON c.parent_id = ct.id
)
SELECT id FROM cat_tree;
```
- Descendant category IDs are resolved in a single round-trip and dynamically bound to `p.category_id IN (%s, ...)`.

### B. Canonical Cache Keying (Zero Collision Guarantee)
Dynamic filter parameters (search text, category IDs, brand IDs, price bounds, sorting keys, and pagination slices) can arrive in arbitrary dictionary order or with empty values.
- Empty values and `None` fields are stripped.
- Keys are sorted alphabetically.
- Canonical JSON string is hashed using SHA-256 and truncated to 16 characters:
```
catalog:list:{sha256(canonical_json)[:16]}
```
- Guarantees deterministic key generation with 0% risk of key collision across different queries.

### C. Single-Flight Mutex Cache Stampede Protection
When a cache key expires or cold traffic hits an unpopulated key, hundreds of concurrent requests could overwhelm the relational database (Cache Stampede / Thundering Herd).
- The first arriving request acquires a distributed Redis mutex key:
```
SET lock:{cache_key} 1 NX EX 5
```
- **Winner:** Queries MySQL, writes result to Redis with configured TTL (60s), and deletes lock. Cache status: `MISS`.
- **Losers:** Poll every 50ms (up to 500ms) to read the populated cache. Cache status: `STAMPEDE_PROTECTED_HIT`.
- **Outage Fallback:** If Redis is down, bypasses mutex directly to MySQL. Cache status: `BYPASS_DOWN`.

```
Client 1 (Winner) ---------> Acquire Lock (NX) -> Queries MySQL -> Populates Redis -> Releases Lock
Client 2 (Waiting) --------> Lock Exists -> Sleep 50ms -> Reads Redis Cache (Hit)
Client 3 (Waiting) --------> Lock Exists -> Sleep 50ms -> Reads Redis Cache (Hit)
```

### D. Automated Mutation Invalidation
To prevent stale reads:
- Every `POST /api/v1/products`, `PATCH /api/v1/products/{id}`, and `DELETE /api/v1/products/{id}` invokes `invalidate_product_cache()`.
- Uses non-blocking `SCAN` iteration (`catalog:list:*`) to delete all listing caches without blocking Redis execution.
- Removes the specific product key (`catalog:product:{id}`).

### E. Optimistic Concurrency Control
Concurrent updates to product inventory and pricing are guarded via versioning:
- Products contain an integer `version` column.
- Updates execute:
```sql
UPDATE products SET ..., version = version + 1 WHERE id = %s
```
- Prevents lost updates during administrative catalog modifications.

---

## 3. Database Schema & Indexing Strategy

- **`products` table indexes:**
  - `PRIMARY KEY (id)`
  - `UNIQUE KEY uq_sku (sku)`
  - `UNIQUE KEY uq_slug (slug)`
  - `KEY idx_category_active (category_id, is_active)`: Supports rapid hierarchical filtering of active products.
  - `KEY idx_brand_active (brand_id, is_active)`: Supports brand catalog queries.
  - `KEY idx_price_active (price, is_active)`: Supports range queries and sorting.
  - `FULLTEXT KEY ft_search (title, description)`: Powers natural-language product discovery.
