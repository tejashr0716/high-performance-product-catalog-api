# Resume Bullet Recommendations

**Project:** High-Performance Product Catalog API  
**Maintainer:** Tejas H R (`https://github.com/tejashr0716`)  
**Repository:** `https://github.com/tejashr0716/high-performance-product-catalog-api`

---

## 1. Verified Evidence-Backed Resume Bullets

These bullet points are strictly derived from actual measured local benchmarks and 100% passing test runs. They conform to the CAR (Context-Action-Result) and STAR frameworks.

### Option 1: Distributed Systems & Backend Focus
> **High-Performance Product Catalog API** | *FastAPI, MySQL 8, Redis, aiomysql, Pydantic, pytest*  
> - Engineered an asynchronous e-commerce catalog API managing **1,020 products**, reducing median P50 query latency by **47.1% (11.51 ms to 6.09 ms)** and scaling throughput by **1.82x (788 to 1,431 req/sec)** via multi-tier Redis caching.  
> - Designed single-flight distributed mutex locks (`SET NX`) to eliminate cache stampedes on cold misses, and implemented ANSI SQL `WITH RECURSIVE` CTEs for multi-tier category hierarchies.  
> - Built automated cache invalidation pipelines with non-blocking Redis `SCAN` operations and established a **20-test passing pytest regression suite (100% pass rate)**.

### Option 2: Database & Data Engineering Focus
> **High-Performance Product Catalog API** | *Python, MySQL, Redis, aiomysql, Docker, pytest*  
> - Architected parameterized ANSI SQL queries with composite indexing and recursive CTEs, resolving deep parent-child category hierarchies in single round-trips without N+1 query overhead.  
> - Implemented canonical SHA-256 key serialization guaranteeing zero cache collisions, optimistic concurrency versioning (`version = version + 1`), and non-destructive soft-archival.  
> - Validated end-to-end resilience under simulated network outages with graceful fallback to primary MySQL, maintaining **100% automated test coverage** across 20 test cases.

### Option 3: Concise Single-Line Bullet (For General SDE Roles)
> - Built a high-concurrency product catalog API in FastAPI/MySQL/Redis, reducing P50 latency by **47.1% (6.09 ms)** at **1,431 RPS** using single-flight stampede mutexes and recursive CTE queries with a **20-test passing pytest suite**.

---

## 2. ATS Technical Keywords
- **Languages & Frameworks:** Python, FastAPI, aiomysql, PyMySQL, Pydantic V2, Uvicorn, asyncio
- **Databases & Caching:** MySQL 8.4, InnoDB, Redis 7.4, ANSI SQL Recursive CTEs, Composite Indexing, Full-Text Search
- **Architectural Concepts:** Distributed Mutex Caching, Single-Flight Pattern, Cache Stampede Mitigation, Cache Invalidation, Canonical Key Hashing, Optimistic Concurrency Control, Graceful Degradation
- **Testing & Tooling:** pytest, pytest-asyncio, HTTPX, JUnit XML, Git, GitHub Actions, PEP 8 standards
