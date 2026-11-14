# Development Bench Environment (ERP-001)

Status: development
Owner: partner
Plan ID: ERP-001

## 1. Overview

This directory defines a local, synthetic-data-only Docker development bench for the ERP runtime and change engine. It is not a production deployment or the shared development host (INF-012).

The environment stands up:
1. **Engine**: a digest-pinned Frappe/ERPNext image with HRMS and the local `apps/engine/change_engine` app mounted in editable mode.
2. **Database**: MariaDB 10.6 configured with `utf8mb4` and InnoDB.
3. **Cache and queue**: two Redis 7.2.7-alpine services. The licence review remains open (Q-15).

Compose project names scope containers and volumes. Database and Redis publish no host ports; the engine binds only to IPv4 loopback for local verification. It must not be exposed to customers or the internet (ADR-0016).

---

## 2. Pinned Version Set

| Component | Version | Source identity | Licence | Role |
|---|---|---|---|---|
| **Frappe Framework** | `v15.126.0` | Base image digest below; packaged source commit UNVERIFIED | MIT | Framework and document metadata |
| **ERPNext** | `v15.124.5` | Image metadata reports `e5cde8c4b9e3f7f567a92ca3e65fd411402b89ce` | GNU GPL v3.0 | Core trading and accounting modules |
| **Frappe HRMS** | `v15.64.8` | Build checks `186900a6e3db4e6f927f1ee20df745bbb082638a` | GNU GPL v3.0 | HR skeleton |
| **Change Engine** | `0.1.0` | Repository local (`apps/engine/change_engine/`) | Founder contribution | DDL plan gate, audited apply, runtime policies |
| **MariaDB** | `10.6` | Image digest in Compose | GNU GPL v2.0 | Relational persistence |
| **Redis** | `7.2.7-alpine` | Image digest in Compose | BSD-3-Clause source; counsel review pending | Cache and queue |

The Frappe/ERPNext base is `frappe/erpnext@sha256:6e016c0fc3aec5b32c14ff7c2ac97523cc864748c83ce75197779b8fe5a665a8`. The cached image reports the versions above, but its Frappe source revision is absent from its metadata. Redis source licence: [upstream](https://github.com/redis/redis/blob/7.2.7/COPYING), accessed 2026-11-11. The exact image digests used here were tested on `linux/amd64`; other architectures are UNVERIFIED.

---

## 3. Quickstart

### Prerequisites
- Docker Engine, Compose v2 and Buildx on a `linux/amd64` development machine.
- A free loopback port, unique Compose project name, and synthetic-only credentials. Docker access grants control over the host; use a trusted local account.

### Step 1: Configure the local project
From the repository root, choose a project and enter unique local-only passwords without putting them in shell history:
```bash
export COMPOSE_PROJECT_NAME=platform-local
export SITE_NAME=synthetic.localhost
export ENGINE_PORT=18111
read -rsp 'Local database root password: ' DB_ROOT_PASSWORD
printf '\n'
read -rsp 'Local site administrator password: ' ADMIN_PASSWORD
printf '\n'
export DB_ROOT_PASSWORD ADMIN_PASSWORD
```
Keep credentials in a local secret store outside the repository. Never use real customer or pilot data.

### Step 2: Build and Start Services
```bash
docker compose --env-file /dev/null -f infra/dev/docker/docker-compose.dev.yml up -d --build
```

### Step 3: Create a synthetic site
Wait for the engine to start, then run this once for the chosen site. It creates a database inside this Compose project's volume.
```bash
docker compose --env-file /dev/null -f infra/dev/docker/docker-compose.dev.yml exec -T engine sh -ec \
  'bench new-site "$SITE_NAME" --db-host "$DB_HOST" --mariadb-user-host-login-scope=% --db-root-password "$DB_ROOT_PASSWORD" --admin-password "$ADMIN_PASSWORD" --install-app erpnext --install-app hrms --install-app change_engine'
```

---

### Step 4: Verify the running site
```bash
python3 infra/dev/docker/verify_dev_bench.py
```
The verifier checks the selected project's running engine, site database and installed apps, app versions, HRMS commit, and both Redis services. It does not prove tenant isolation, accounting correctness, or adapter conformance. The separate automated regression tests live in `infra/dev/docker/tests/`.

Stop only the selected project with `docker compose --env-file /dev/null -f infra/dev/docker/docker-compose.dev.yml stop`. Its synthetic volumes remain; removing volumes destroys their data.
