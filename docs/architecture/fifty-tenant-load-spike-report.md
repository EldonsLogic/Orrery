# 50-Tenant Load Spike Report (`ERP-002`)

Status: draft
Owner: partner
Plan ID: ERP-002

Empirical evaluation of multi-tenant density, provisioning scaling, resource footprint, and concurrent HTTP/DB isolation for **50 synthetic tenant sites** (`load-001.localhost` .. `load-050.localhost`) on one pinned Frappe/ERPNext v15 Compose bench pool ([docker-compose.dev.yml](../../infra/dev/docker/docker-compose.dev.yml)).

All data in this report is synthetic (`load-001.localhost` .. `load-050.localhost`). No real or pilot data was used.

## How to run

- **Offline contract and unit suite (CI):**
  ```bash
  cd infra/dev/docker
  python3 -m unittest discover -s tests -v
  ```
- **Dry-run plan check:**
  ```bash
  python3 infra/dev/docker/run_50_tenant_load_spike.py --compose-project erp002-dry --dry-run
  ```
- **Live 50-tenant spike runner:** [run_50_tenant_load_spike.py](../../infra/dev/docker/run_50_tenant_load_spike.py) (tested against a disposable loopback Compose stack on port `18222`, torn down with `down -v` after measurement).

## Pinned stack under test

| Service | Version / Config |
|---|---|
| Frappe / ERPNext / HRMS / `change_engine` | `v15.126.0` / `v15.124.5` / `v15.64.8` / `0.1.0` |
| Gunicorn (`engine-1`) | `--workers=2 --threads=4 --worker-class=gthread` (`8` request threads total) |
| MariaDB (`mariadb-1`) | `11.4.13-MariaDB-ubu2404` (`max_connections=151`, `open_files_limit=32270`, `innodb_flush_log_at_trx_commit=1` during load) |
| Redis (`redis-cache-1`, `redis-queue-1`) | `7.2.7-alpine` |

## 1. Provisioning & Schema Density

Each freshly installed `erpnext + hrms + change_engine` site creates **`852–854` InnoDB tables** (`~53 MB` logical data + index). At **50 tenants**, one bench pool holds **`42,600` InnoDB tables** (`2,525.99 MB` logical data + index, `5.7 GiB` physical `/var/lib/mysql`, `1.94–2.13 MiB` in `sites/` before tenant attachments).

### Provisioning throughput vs MariaDB tuning

Cold `bench new-site` on the pinned stack takes `~240s` per site (`~3.3 hours` serially for 50 sites). Cloning from a logical SQL dump (`9,039,954 bytes`, dumped in `3.49s–3.91s`) with `innodb_flush_log_at_trx_commit=2` during bulk restore dramatically reduces initial time, **but degrades non-linearly under MariaDB's default `128 MiB` buffer pool / `2000` `table_open_cache` and high DDL concurrency**:

| Phase / Sites | MariaDB Pool / `table_open_cache` | Workers | Outcome / Timing | Notes |
|---|---|---|---|---|
| `load-001` cold `bench new-site` | `128 MiB` / `2000` | 1 | `~240s` (`~4.0 min`) | Baseline cold install (`erpnext`, `hrms`, `change_engine`) |
| Single-site SQL clone baseline | `128 MiB` / `2000` | 1 | `40.50s` (`~6x` faster) | `mariadb < template.sql` + per-site Fernet `encryption_key` |
| High-concurrency clone probe | `128 MiB` / `2000` | 8 | `~88s/DB` (`~700s` wall) | Severe InnoDB `dict_sys` / DDL latch contention |
| `14..21` (17 -> 21 DBs, 17,892 tables) | `128 MiB` / `2000` | 2 | `8/8` in `367.20s` (`91.58s` mean/site, `68.62s` p50) | `Open_tables` saturated (`2000/2000`), `Opened_tables=100,663` |
| `22..27` (21 -> 27 DBs, ~24k tables) | `128 MiB` / `2000` | 2 | `5/8` took `481.9s` (`~96.4s` wall/site) | **2.4x degradation** under `128 MiB` buffer pool thrashing |
| `28..35` (29 -> 35 DBs, 29,820 tables) | **`1 GiB` / `8192`** | 2 | `8/8` in `428.04s` (`106.86s` mean/site, `104.64s` p50) | Initial buffer-pool warmup period |
| `36..40` (35 -> 40 DBs, 34,080 tables) | **`1 GiB` / `8192`** | 2 | `5/5` in **`161.32s`** (`56.25s` mean/site, `32.3s` wall/site) | Steady-state tuned clone throughput |
| `41..45` (40 -> 45 DBs, 38,340 tables) | **`1 GiB` / `8192`** | 2 | `5/5` in **`156.19s`** (`54.24s` mean/site, `31.2s` wall/site) | Steady-state tuned clone throughput |
| `46..50` (45 -> 50 DBs, 42,600 tables) | **`1 GiB` / `8192`** | 2 | `5/5` in **`156.80s`** (`54.55s` mean/site, `31.4s` wall/site) | Final 50 DBs / `42,600` tables |

**Provisioning finding for `PLT-003`:** Even with tuned MariaDB (`1 GiB` buffer pool, `8192` table cache), synchronous logical SQL cloning takes `~54–56s` per site (`~31s` wall at 2 workers). Customer-facing onboarding cannot run `bench new-site` or logical SQL restore inline; `PLT-003` should claim from a **pre-warmed pool of idle tenant sites** (sub-second assignment) replenished asynchronously in the background (or via `mariabackup`/CoW snapshots).

## 2. 50-Tenant Isolation & Cold-Cache Warming

- **Per-site MariaDB credential isolation:** Cross-tenant `SELECT` from `load-001.localhost` DB user against `load-050.localhost` `tabUser` failed cleanly with MariaDB `errno 1142` (`SELECT command denied`).
- **Per-site secrets & API key generation (`__Auth` Fernet encryption):** Seeding unique `Administrator` API keys/secrets across all 50 sites completed in `58.67s`.
- **Sequential 50-site HTTP/Redis warm (`50/50` HTTP `200`):**
  - `GET /api/method/ping`: mean `102.54 ms`, p50 `99.80 ms`, p95 `125.10 ms`, max `147.05 ms`
  - Authenticated `GET /api/method/frappe.auth.get_logged_user`: mean `53.80 ms`, p50 `47.30 ms`, p95 `77.49 ms`, max `142.96 ms`

## 3. Concurrent Load Results (50 Tenants, `c = 10, 25, 50, 100`)

Four waves of **250 requests each** (`1,000` total requests) spread across all 50 sites (`40%` `ping`, `40%` authenticated `get_logged_user`, `20%` authenticated `POST /api/resource/ToDo` asserting unique per-request tenant tag in response) with `innodb_flush_log_at_trx_commit = 1`:

| Concurrency | Throughput (RPS) | HTTP 200 / Total | Isolation Mismatches | Overall p50 (ms) | Overall p95 (ms) | Overall p99 (ms) | Overall Max (ms) | Write `ToDo` p50 / p95 (ms) |
|---|---|---|---|---|---|---|---|---|
| `c=10` | `39.66` | `250 / 250` (`100%`) | `0` | `122.44` | `979.91` | `1,210.03` | `1,306.25` | `596.84` / `1,207.18` |
| `c=25` | `79.53` | `250 / 250` (`100%`) | `0` | `266.07` | `614.40` | `956.06` | `1,131.17` | `428.80` / `970.97` |
| `c=50` | **`93.40`** | `250 / 250` (`100%`) | `0` | `434.80` | `736.93` | `812.66` | `1,117.32` | `546.23` / `822.87` |
| `c=100` | `90.07` | `250 / 250` (`100%`) | `0` | `876.27` | `1,434.06` | `1,497.95` | `1,699.03` | `927.10` / `1,491.58` |

Key observations:
1. **Zero errors & zero cross-tenant leaks:** All `1,000` concurrent multi-tenant requests succeeded (`200 OK`) with `0` timeouts and `0` response mismatches.
2. **Thread-pool saturation knee at `~93 RPS` (`c=50 -> c=100`):** With `workers=2 --threads=4` (`8` worker threads), throughput plateaus at `~90–93 RPS` above `c=50`; pushing concurrency from `50` to `100` doubles p50 (`434.80 ms -> 876.27 ms`) and p95 (`736.93 ms -> 1,434.06 ms`) due to Gunicorn queue wait, while `Max_used_connections` on MariaDB remained flat at **`17`** (`11.3%` of `151`).
3. **First-wave (`c=10`) cold table warmup effect:** `c=10` had higher `ToDo` write p95 (`1,207 ms`) than `c=25` (`971 ms`) because the first write wave populated InnoDB buffer pool pages and `tabToDo` table handles across all 50 databases (`mariadb-1` RSS rose `+413 MiB` during `c=10`).

## 4. Resource Footprint Progression (50 Tenants)

| Stage | `engine-1` RSS (2 workers) | `mariadb-1` RSS | `redis-cache-1` Used / RSS | `redis-cache` Keys (`dbsize`) | MariaDB `Opened_tables` |
|---|---|---|---|---|---|
| 17 DBs idle (`128 MiB` / `2000`) | `273.0 MiB` (`115.4 MiB`/worker) | `1,289.2 MiB` | `1.37 MiB` | `9` | `80,093` |
| 50 DBs idle (`1 GiB` / `8192`) | `275.3 MiB` (`115.4 MiB`/worker) | `5,601.3 MiB` (`5.47 GiB`) | `1.37 MiB` | `9` | `395,216` |
| After 50-site sequential warm | `286.2 MiB` (`122.1 MiB`/worker) | `6,853.6 MiB` (`6.69 GiB`) | `22.74 MiB` (`28.3 MiB` cont.) | `1,252` (`0` evicted) | `567,545` |
| After `c=10` (`250` reqs) | `319.5 MiB` | `7,266.3 MiB` (`7.10 GiB`) | `24.46 MiB` (`32.7 MiB` cont.) | `1,404` (`0` evicted) | `610,788` |
| After `c=100` (`1,000` reqs total) | **`326.1 MiB`** (`141.5 MiB`/worker) | **`7,270.4 MiB`** (`7.10 GiB`) | **`25.01 MiB`** (`32.6 MiB` cont.) | **`1,449`** (`0` evicted) | `739,071` |

`redis-queue-1` remained between `4.73 MiB` and `6.54 MiB` throughout (no async queue workers were running in `docker-compose.dev.yml`).

### Bottleneck Diagnosis

1. **Primary bottleneck — MariaDB per-table memory and `table_open_cache` churn (`~145 MiB` MariaDB RSS per empty site):**
   - `50` sites × `852` tables = `42,600` InnoDB tables. Even with minimal customer rows, InnoDB data dictionary cache + `8,192` open table handles + `1 GiB` buffer pool consumes **`7.10 GiB` RSS** once all 50 sites are active.
   - Because `table_open_cache` (`8,192`) is smaller than `42,600` total tables, cross-site bursts continually evict and reopen tables (**`~43,000` `Opened_tables` per 250-request wave**).
2. **Python app-server (`engine-1`) memory is NOT the bottleneck:**
   - Each Gunicorn worker grew by only **`+26 MiB`** (`115.4 MiB -> 141.5 MiB`, i.e., `~1.05 MiB` per active site across 2 workers) after exercising all 50 sites.
3. **Redis cache footprint is modest (`~0.47 MiB` / `~29` keys per active site):**
   - `25.01 MiB` total across 50 warm sites (`0` evictions).

## 5. Recommendations for `PLT-003`, `INF-010`, and Bench Defaults

1. **Shard MariaDB at 50–100 active tenants per DB node (`INF-010`):**
   - Do not pack >100 ERPNext+HRMS sites onto a single MariaDB instance. At `~145 MiB` baseline RSS/site before real transaction growth, a `16–32 GiB` MariaDB shard cleanly supports `50–100` active SMB tenants with room for hot working sets.
2. **Production MariaDB sizing (`INF-010`):**
   - Raise `table_open_cache >= 32768` (with `open_files_limit >= 131072` and `table_definition_cache >= 16384`) and `innodb_buffer_pool_size` to `40–50%` of DB node RAM so active multi-tenant bursts do not churn `Opened_tables`.
   - Keep `infra/dev/docker/my.cnf` lightweight for single-tenant developer laptops (developers should not allocate 8 GiB RAM by default), and document scale overrides cleanly.
3. **Pre-warmed site pool for instant onboarding (`PLT-003`):**
   - Never run `bench new-site` (`~240s`) or synchronous SQL restore (`~55s`) in the tenant signup request path. Maintain a pre-warmed site pool per bench shard (sub-second tenant claim) replenished asynchronously.
4. **Horizontal / multi-worker Gunicorn scaling (`INF-010`):**
   - `2` workers × `4` threads (`8` slots) saturates at `~93 RPS`. Production engine pods should scale worker count to CPU cores (`2 * cores + 1` or horizontally behind the platform gateway) and pair with dedicated `bench worker` pods (`QA-013` will measure async queue/report/ZATCA workloads).
