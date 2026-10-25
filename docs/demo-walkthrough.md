# Demonstration & Interview Walkthrough Guide

**Project:** High-Performance Product Catalog API  
**Maintainer:** Tejas H R (`https://github.com/tejashr0716`)  

---

## 1. Purpose of this Demonstration

This guide outlines the exact, step-by-step walkthrough to showcase the catalog API during technical interviews and engineering reviews. It demonstrates real system behavior across:
1. Live health monitoring and connection status.
2. Recursive category search.
3. Cold vs. warm cache transitions and latency reduction.
4. Mutation-triggered automatic cache invalidation.
5. High-concurrency stampede mutex coalescing.

---

## 2. Walkthrough Script

### Step 1: Health & Observability Check
Start the application and inspect service readiness:
```bash
curl -i http://localhost:8000/health
```
**Expected Response:**
```json
{
  "status": "HEALTHY",
  "service": "Product Catalog API",
  "mysql_connected": true,
  "redis_connected": true,
  "timestamp": "2026-10-25T17:30:00.000000Z"
}
```

### Step 2: Recursive Hierarchical Category Filtering
Query products under root Category `1` (Electronics). Demonstrate that it automatically returns products belonging to its nested child categories (`4: Audio`, `5: Laptops`, `6: Smartphones`):
```bash
curl -i "http://localhost:8000/api/v1/products?category_id=1&page_size=3"
```
**Key Observations:**
- Response header contains `X-Cache-Status: MISS` (on first hit).
- Items have `category_id: 4`, `category_id: 5`, etc.
- Demonstrates ANSI SQL `WITH RECURSIVE cat_tree` CTE execution.

### Step 3: Cold vs Warm Cache Latency Drop
Run the exact same request again immediately:
```bash
curl -i "http://localhost:8000/api/v1/products?category_id=1&page_size=3"
```
**Key Observations:**
- Response header changes to `X-Cache-Status: HIT`.
- `X-Process-Time-Ms` drops from ~11.5ms to ~6.0ms (-47% latency reduction).
- Payload is identical, served directly from Redis.

### Step 4: Product Mutation & Automatic Cache Invalidation
Update a product's price and verify that cached listings are instantly purged:
```bash
# Update product 1 title
curl -i -X PATCH "http://localhost:8000/api/v1/products/1" \
  -H "Content-Type: application/json" \
  -H "X-Admin-Key: catalog-admin-secret-key-at-least-32-chars-long" \
  -d '{"title": "Sony WH-1000XM5 Premium Noise-Cancelling Headphones"}'
```
Now retrieve product 1 again:
```bash
curl -i "http://localhost:8000/api/v1/products/1"
```
**Key Observations:**
- `X-Cache-Status` is `MISS` (the previous `catalog:product:1` cache was purged).
- Title reflects the updated value immediately.
- Zero stale read window.

### Step 5: Web UI Dashboard Walkthrough
1. Open `http://localhost:8000/` in the browser.
2. Type "Headphones" in the search box; observe the 300ms debouncing indicator.
3. Select "Electronics" category; observe the real-time filter chips and pagination metadata.
4. Note the live `Cache Status` badge displaying `MISS` on initial filter change and transitioning to `HIT` on subsequent interactions.
