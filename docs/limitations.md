# Technical Constraints, Trade-offs & Future Roadmap

**Project:** High-Performance Product Catalog API  
**Maintainer:** Tejas H R (`https://github.com/tejashr0716`)  

---

## 1. Documented Constraints & Trade-offs

### A. Non-blocking Cache Invalidation via SCAN
- **Current Implementation:** When a product mutation occurs, `invalidate_product_cache` iterates over keys matching `catalog:list:*` using `SCAN` with cursor batches of 100.
- **Trade-off:** While non-blocking and safe for small-to-medium datasets (thousands of cached query variants), high-volume production deployments with millions of active listings would benefit from tagged cache groups or Redis sets maintaining reverse lookup mappings.

### B. Mutex Wait Polling Interval
- **Current Implementation:** In `fetch_with_stampede_protection`, concurrent requests encountering an active mutex lock poll Redis every 50ms (up to 10 attempts = 500ms max).
- **Trade-off:** Simple, robust, and zero additional dependency. In ultra-low latency microsecond services, Redis Pub/Sub keyspace notifications could notify waiting workers instantly upon lock release.

### C. Single Node Primary MySQL
- **Current Implementation:** Connects to a single MySQL instance with connection pooling (`aiomysql`).
- **Trade-off:** Highly reliable for single-region systems. Enterprise scaling would introduce read replicas with ProxySQL or Vitess to distribute read traffic horizontally across multiple replica nodes.

---

## 2. Future Architectural Roadmap

1. **Redis Cluster & Sharding Support:**
   - Migrate from single-instance Redis to Redis Cluster with hash slots for horizontal cache scaling.
2. **Elasticsearch / Meilisearch Integration:**
   - Supplement MySQL fulltext search with dedicated vector or fuzzy search engines for typo tolerance and semantic embeddings.
3. **Change Data Capture (CDC) via Debezium & Kafka:**
   - Decouple cache invalidation from synchronous API request threads by consuming MySQL binlog events via Kafka and invalidating Redis asynchronously.
4. **GraphQL / gRPC Catalog Interfaces:**
   - Provide typed gRPC endpoints for internal microservice communication and GraphQL for mobile client payload slimming.
