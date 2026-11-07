# Development Bench Environment (ERP-001)

Status: active
Owner: partner
Plan ID: ERP-001

## 1. Overview

This directory defines the reproducible local Docker development bench for the Orrery ERP runtime (Part 3) and change engine (Part 2 apply layer).

The environment stands up:
1. **Engine Container (`ce-engine-dev`)**: Official Frappe/ERPNext base image extended with pinned Frappe HRMS and the local `apps/engine/change_engine` app mounted in editable development mode.
2. **Relational Database (`ce-mariadb`)**: MariaDB 10.6 configured with `utf8mb4` character set and InnoDB engine settings.
3. **Cache & Queue (`ce-redis-cache`, `ce-redis-queue`)**: Redis 7.2.7-alpine pinned to the BSD-3-Clause release stream (resolving Q-15 for the dev environment).

Per ADR-0016, the engine runs headless behind the platform gateway.

---

## 2. Pinned Version Set

| Component | Pinned Version / Tag | Upstream Commit / Digest | Licence | Role in Orrery |
|---|---|---|---|---|
| **Frappe Framework** | `v15.126.0` | `53bae3ef2550ca96320f036f581446783cd11b72` | MIT | Web framework, DocType schema, REST API, auth |
| **ERPNext** | `v15.124.5` | `e5cde8c4b9e3f7f567a92ca3e65fd411402b89ce` | GNU GPL v3.0 | Core trading and accounting modules |
| **Frappe HRMS** | `v15.64.8` | `186900a6e3db4e6f927f1ee20df745bbb082638a` | GNU GPL v3.0 | Payroll and regional HR compliance skeleton |
| **Change Engine** | `0.1.0` | Repository local (`apps/engine/change_engine/`) | Founder contribution | DDL plan gate, audited apply, runtime policies |
| **MariaDB** | `10.6` | Official Docker `mariadb:10.6` | GNU GPL v2.0 | Multi-tenant relational persistence |
| **Redis** | `7.2.7-alpine` | Official Docker `redis:7.2.7-alpine` | BSD-3-Clause | Session cache and Celery background queue |

---

## 3. Quickstart

### Prerequisites
- Docker Engine 24+ and Docker Compose v2.

### Step 1: Configure Environment
Copy `.env.example` to `.env` and set local passwords:
```bash
cp .env.example .env
```
*(Never commit `.env` to version control).*

### Step 2: Build and Start Services
```bash
docker compose -f docker-compose.dev.yml up -d --build
```

### Step 3: Run Verification Test
```bash
python3 verify_dev_bench.py
```

---

## 4. Tenant Site Provisioning (ERP-003 Preview)

To provision a new tenant site inside the bench:
```bash
docker exec -it ce-engine-dev bench new-site tenant1.localhost \
  --mariadb-root-password "${DB_ROOT_PASSWORD}" \
  --admin-password "${ADMIN_PASSWORD}" \
  --install-app erpnext \
  --install-app hrms \
  --install-app change_engine
```

To list installed apps on an active site:
```bash
docker exec -it ce-engine-dev bench --site dev.localhost list-apps
```
