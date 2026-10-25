# Setup & Local Installation Guide

**Project:** High-Performance Product Catalog API  
**Maintainer:** Tejas H R (`https://github.com/tejashr0716`)  

---

## 1. System Requirements

- **Operating System:** macOS (Apple Silicon / Intel) or Linux (Ubuntu 22.04+)
- **Python:** Version 3.11, 3.12, 3.13, or 3.14
- **Database:** MySQL 8.0+ running on port `3307` or `3306`
- **Cache:** Redis 6.0+ running on port `6379`

---

## 2. Step-by-Step Installation

### Clone Repository & Create Virtual Environment
```bash
git clone https://github.com/tejashr0716/high-performance-product-catalog-api.git
cd high-performance-product-catalog-api

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### Configure Environment Variables
Copy the template configuration file:
```bash
cp .env.example .env
```
Ensure `.env` matches your local MySQL and Redis parameters:
```ini
DB_HOST=127.0.0.1
DB_PORT=3307
DB_USER=root
DB_PASSWORD=
DB_NAME=catalog_db
DB_SOCKET=/tmp/mysql3307.sock

REDIS_HOST=127.0.0.1
REDIS_PORT=6379

ADMIN_API_KEY=catalog-admin-secret-key-at-least-32-chars-long
```

---

## 3. Database Migration & Seeding

### Create Schema & Tables
Apply the initial schema:
```bash
mysql -u root -P 3307 --socket=/tmp/mysql3307.sock -e "CREATE DATABASE IF NOT EXISTS catalog_db;"
mysql -u root -P 3307 --socket=/tmp/mysql3307.sock catalog_db < database/schema.sql
```

### Seed Realistic Catalog Data
Populate 15 categories, 15 brands, and 1,020 realistic products:
```bash
python scripts/seed.py
```
Output:
```
[Database] Connected to catalog_db via /tmp/mysql3307.sock
[Seeding] Created 15 hierarchical categories.
[Seeding] Created 15 brands.
[Seeding] Successfully inserted 1,020 catalog products.
```

---

## 4. Running the Application

Start the FastAPI application with Uvicorn:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Endpoints available:
- **Web UI Dashboard:** `http://localhost:8000/`
- **Interactive OpenAPI Documentation:** `http://localhost:8000/docs`
- **Service Health Check:** `http://localhost:8000/health`

---

## 5. Verification & Testing

### Run Automated Unit & Integration Tests
```bash
PYTHONPATH=. pytest tests/ -v --junitxml=artifacts/test-results.xml
```

### Run Performance Benchmark Harness
```bash
python scripts/benchmark.py
```
Outputs:
- `artifacts/benchmark-results.json`
- `artifacts/validation-report.md`
