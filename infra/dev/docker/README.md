# Development Bench Environment (ERP-001)

Status: development
Owner: partner
Plan ID: ERP-001

## 1. Overview

This directory defines a local, synthetic-data-only Docker development bench for the ERP runtime and change engine. It is not a production deployment or the shared development host (INF-012).

The environment stands up:
1. **Engine**: a digest-pinned Frappe/ERPNext image with HRMS and the local `apps/engine/change_engine` app mounted in editable mode.
2. **Database**: MariaDB 11.4 configured with `utf8mb4` and InnoDB.
3. **Cache and queue**: two Redis 7.2.7-alpine services. The licence review remains open (Q-15).

Compose project names scope containers and volumes. Database and Redis publish no host ports; the engine binds only to IPv4 loopback for local verification. It must not be exposed to customers or the internet (ADR-0016). The internal-only shape with no host port, and the engine's route guard, are in [HEADLESS.md](HEADLESS.md) (ERP-020).


### Redis authentication and network (INF-015)
Both Redis services require a password, and only engine services can reach them.
- **Where the password comes from.** `REDIS_PASSWORD` is minted fresh for every stack by the runner that starts it (`run_real_bench_ci.py`, `isolation/run_isolation_suite.py`, `smoke_headless_engine.py`) with `secrets.token_urlsafe(32)`. `run_real_bench_ci.py --reuse-project` instead takes the running stack's password from the environment, like `ENGINE_INTERNAL_TOKEN`, and stops without it. For a manual bench, generate it as in Step 1. No value is committed or put on a command line; Compose passes it to the containers by name from the environment.
- **What is redacted.** The runners never print the password themselves. Before printing captured child output they replace every password, secret and token value from their environment, and any `redis://:<password>@` credential, with `<REDACTED>`: `run_real_bench_ci.py` failure diagnostics (`compose logs`) and verifier output, `smoke_headless_engine.py` Compose, site-creation and sidecar errors, and `isolation/run_isolation_suite.py` provisioning errors. Not redacted: output the runners stream live (the `compose up --build` output and the CE-SEC-005 and SEC-004 test output) and the engine's own log files. The remaining engine-side risk: Frappe v15 `get_redis_conn` may log the full `redis_queue` URL, password included, on a Redis connection error (`frappe/utils/background_jobs.py`, version-15 branch, accessed 2026-11-21; UNVERIFIED against the pinned image). Treat bench logs as holding the dev bench's Redis password.
- **Where it lives.** In the Redis and engine containers' environment (like the database root password), in an owner-only `/tmp/redis.conf` inside each Redis container (`requirepass`, `protected-mode yes`; never on a command line), and in the bench's `sites/common_site_config.json` (mode 600) as `redis://:<password>@redis-cache:6379` for `redis_cache` and `redis://:<password>@redis-queue:6379` for `redis_queue` and `redis_socketio`.
- **Fail closed.** An empty, non-URL-safe or shorter than 32 characters password stops the Redis containers and the engine entrypoint, so no stack runs with open or weakly protected Redis. Each Redis start removes the old `/tmp/redis.conf` before writing a new one, so a stop and start works on hosts with `fs.protected_regular` set. Restarting a project with a new password recreates all its services together.
- **Network.** Redis is attached only to the internal `redis_internal` network, shared with the engine (and the isolation suite's worker). MariaDB, the gateway-facing `engine_internal` network and any other container cannot reach it, and Redis publishes no host port.
- **Checks.** `verify_dev_bench.py` proves each Redis answers an authenticated PING and refuses an unauthenticated one with `NOAUTH` (an exec error, DNS miss or empty reply fails the check). `smoke_headless_engine.py` proves a container on `engine_internal` cannot reach `redis-cache:6379` or `redis-queue:6379` (DNS miss or connection refused), while the same probe reaches the engine and the engine answers an authenticated PING. `tests/test_inf_015_redis_auth.py` and `tests/test_inf_015_redis_hardening.py` check every Compose stack, the start scripts and the runners offline. To use `redis-cli` by hand: `docker compose ... exec redis-cache sh -c 'REDISCLI_AUTH="$REDIS_PASSWORD" redis-cli ping'`.
- **Residual risk (INF-005).** Code running inside the engine or a worker holds the password and can still read every tenant's keys (key-prefix isolation only). The password sits in the Redis and engine containers' environment, readable through `docker inspect` and `/proc/*/environ` by anyone with Docker or container access. Both Redis services use one shared password on the built-in `default` user, which keeps full admin rights. Production Redis is INF-005's scope: a file-mounted secret and per-service ACL users without `@admin` and `@dangerous`.

### BPL-027 bench class in real-bench CI (BPL-046)
`run_real_bench_ci.py` layers `docker-compose.bpl027-test.yml` on its stack (read-only mounts of `services/blueprint`, `contracts`, `docs/brand/tools` and `docs/brand/tokens`). As its last phase it installs the pins of `services/blueprint/requirements.txt` except pytest into the bench environment (test-only, fetched from the package index; transitive dependencies are not locked), provisions a fresh `bpl027-*.localhost` site and runs `TestBpl027FixtureRealAdapter` inside the engine container with `BPL027_BENCH_SITE` and `REQUIRE_BPL027_LIVE=1`. A failure, any skip, or fewer tests than `BPL027_MINIMUM_TESTS` fails the run. A `--reuse-project` stack must have been started with the same override, or this phase fails.

Every site the runner provisions gets the index sync of `scripts/provision_tenant_site.py` (BPL-046): Frappe's own `updatedb` on every table, sending only the `ADD INDEX` statements (the `creation` index of `sort_field = creation` tables, missing `search_index` indexes) and failing on any other DDL, so the engine's first schema sync of a table adds nothing the DDL gate has not approved.

---

## 2. Pinned Version Set

| Component | Version | Source identity | Licence | Role |
|---|---|---|---|---|
| **Frappe Framework** | `v15.126.0` | Base image digest below; packaged source commit UNVERIFIED | MIT | Framework and document metadata |
| **ERPNext** | `v15.124.5` | Image metadata reports `e5cde8c4b9e3f7f567a92ca3e65fd411402b89ce` | GNU GPL v3.0 | Core trading and accounting modules |
| **Frappe HRMS** | `v15.64.8` | Build checks `186900a6e3db4e6f927f1ee20df745bbb082638a` | GNU GPL v3.0 | HR skeleton |
| **Change Engine** | `0.1.0` | Repository local (`apps/engine/change_engine/`) | Founder contribution | DDL plan gate, audited apply, runtime policies |
| **MariaDB** | `11.4` | Image digest in Compose | GNU GPL v2.0 | Relational persistence |
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
REDIS_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
export DB_ROOT_PASSWORD ADMIN_PASSWORD REDIS_PASSWORD
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
Dev bench only: the passwords come from the container's environment, so they are not typed on your command line, but the `bench new-site` process inside the container carries them as arguments, visible to anyone who can list processes in that container. Do not reuse this pattern for any shared or hosted environment.

---

### Step 4: Verify the running site
```bash
python3 infra/dev/docker/verify_dev_bench.py
```
The verifier checks the selected project's running engine, site database and installed apps, app versions, HRMS commit, both Redis services, and that the site answers `/api/method/ping` on `127.0.0.1:${ENGINE_PORT}` (default 8000; set `ENGINE_PORT` if you changed it). It does not prove tenant isolation, accounting correctness, or adapter conformance. The separate automated regression tests live in `infra/dev/docker/tests/`.

### Known limits of this spike
- HRMS is pinned to a commit, but its transitive Python dependencies are installed without a lock file or hashes, so a rebuild can pull newer versions of them.
- Compose runs no worker, scheduler or socketio service, so background jobs, scheduled jobs and realtime updates never run. Anything that depends on them is untested on this bench.

Stop only the selected project with `docker compose --env-file /dev/null -f infra/dev/docker/docker-compose.dev.yml stop`. Its synthetic volumes remain; removing volumes destroys their data.
