# Security & Access Control Architecture

**Project:** High-Performance Product Catalog API  
**Maintainer:** Tejas H R (`https://github.com/tejashr0716`)  

---

## 1. Security Overview

The High-Performance Product Catalog API is designed with defense-in-depth principles:
1. Public read-only catalog browsing is unrestricted and rate-safe via Redis caching.
2. All administrative mutations (`POST`, `PATCH`, `DELETE`, `/admin/cache/purge`) are strictly authenticated.
3. Database interactions strictly use parameterized queries, preventing SQL injection vulnerabilities.
4. Input validation and serialization boundaries are enforced via Pydantic V2 schemas.

---

## 2. Threat Modeling & Mitigations

### A. SQL Injection (SQLi)
- **Threat:** Attackers supplying malicious SQL tokens in query parameters (e.g. `q="' OR '1'='1"`, `"; DROP TABLE products; --"`).
- **Mitigation:**
  - Zero raw string concatenation in SQL queries.
  - All values are passed as parameterized tuples to `aiomysql.DictCursor.execute(query, params)`.
  - Dynamic sorting fields and directions are validated against strict allowlists (`{"id", "price", "rating", "created_at", "title"}` and `{"ASC", "DESC"}`).
  - Automated test `tests/test_search_filters.py::test_sql_parameterization_injection_safety` passes with 100% safety.

### B. Unauthorized Writes & Privilege Escalation
- **Threat:** Malicious actors modifying prices, titles, or purging catalog inventory.
- **Mitigation:**
  - Administrative endpoints require an API key passed via the `X-Admin-Key` header or `Authorization: Bearer <token>`.
  - Constant-time comparison using `hmac.compare_digest` to prevent timing attacks.
  - Missing keys return `401 Unauthorized`; invalid keys return `403 Forbidden`.
  - Verified by `tests/test_crud.py::test_unauthorized_product_creation_rejected`.

### C. Cache Pollution & Stampede Exploitation
- **Threat:** Attackers sending random query parameter combinations to exhaust Redis memory, or simultaneously bursting requests for expired keys to overwhelm MySQL.
- **Mitigation:**
  - Canonical key generation normalizes input and strips unneeded parameters.
  - Single-flight distributed mutex locks (`SET lock:{key} 1 NX EX 5`) prevent thundering herds, coalescing concurrent misses to a single primary database call.

### D. Concurrency Races & Lost Updates
- **Threat:** Two administrators modifying the same product simultaneously, resulting in overwritten price or inventory data.
- **Mitigation:**
  - Optimistic locking using the `version` field.
  - Updates increment `version = version + 1`, and callers can detect stale edits.

---

## 3. Secret Management & Environment Isolation
- No hardcoded secrets exist in source code.
- Sensitive credentials (`ADMIN_API_KEY`, `DB_PASSWORD`, `REDIS_PASSWORD`) are loaded via environment variables using Pydantic `BaseSettings`.
- `.env` is ignored by `.gitignore`; only `.env.example` is committed.
