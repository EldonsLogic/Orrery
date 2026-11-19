# 50-Tenant Load Spike Report (`ERP-002`)

Status: draft
Owner: partner
Plan ID: ERP-002

Empirical evaluation of multi-tenant density, provisioning scaling, resource footprint, and concurrent HTTP load for **50 synthetic tenant sites** (`load-001.localhost` .. `load-050.localhost`) on one pinned Frappe/ERPNext v15 Compose bench pool ([docker-compose.dev.yml](../../infra/dev/docker/docker-compose.dev.yml)).

All data in this report is synthetic (`load-001.localhost` .. `load-050.localhost`). No real or pilot data was used.

## Scope and limits (read first)

Per AGENTS principle 10 and RULES 8 and 44, everything below is either a **measurement from one run** or an **`UNVERIFIED` hypothesis**; each is labelled.

1. **Sites are template clones, not `ERP-003` provisioning.** Sites `load-002`..`load-050` were made by restoring one logical SQL dump of the template site `load-001` and writing a fresh Fernet `encryption_key` plus a new per-site DB user into `site_config.json`. This is not the path `ERP-003` will use to provision tenants. Consequences: (a) any value encrypted under the template's `encryption_key` (Password fields, encrypted `__Auth` entries) is undecryptable on a clone; the run did not enumerate these, so how many exist in the pinned stack is `UNVERIFIED` (per-site API keys were generated after cloning, so the REST calls did not touch them); (b) clones inherit the template's data and the same Administrator password hash (one shared `ADMIN_PASSWORD` from the environment); (c) the spike did not run `ERP-003`'s hooks, Blueprint application or per-tenant company setup. Density, footprint and latency here are therefore for **empty cloned sites**, and carrying them over to `PLT-003` is `UNVERIFIED`. The pre-warmed-pool recommendation stands as a design direction, not as a measured result.
2. **Isolation evidence is limited.** Only the MariaDB per-site credential check (`errno 1142`, section 2) is a real isolation observation. The in-wave HTTP checks cannot detect wrong-site routing (see section 3). The authoritative isolation proof is the `SEC-004` live suite, not this spike.
3. **Host hardware was not recorded in this run.** CPU model, core count, RAM and Docker VM limits of the measuring machine are `UNVERIFIED`, so the throughput numbers (including the `~93 RPS` knee) are not reproducible as stated and must not be read as a capacity figure. The runner now records `host` (`docker info` CPU and memory, host CPU model) in its JSON output; a re-run is needed to fill this in.
4. **Single run, small sample.** `1,000` requests in four waves of `250`, one run, no repeats, no confidence intervals.

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
| MariaDB (`mariadb-1`) | `11.4.13-MariaDB-ubu2404` (`max_connections=151`, `open_files_limit=32270`, `innodb_flush_log_at_trx_commit=1` during load); tuned settings below |
| Redis (`redis-cache-1`, `redis-queue-1`) | `7.2.7-alpine` |

### MariaDB settings used (reproducible)

Two configurations were measured. The exact tuned settings are in [my.load-spike.cnf](../../infra/dev/docker/my.load-spike.cnf) (not mounted by default; the dev `my.cnf` stays light).

| Phase | `innodb_buffer_pool_size` | `table_open_cache` | `innodb_flush_log_at_trx_commit` | Other |
|---|---|---|---|---|
| Sites `1..27` | `128 MiB` (image default) | `2000` (image default) | `2` during bulk clone restore only, else `1` | untouched |
| Sites `28..50` and all load waves | `1 GiB` (`1073741824`) | `8192` | `2` during bulk clone restore only, `1` for all load waves | untouched |

The tuned values were applied at runtime between batches with `SET GLOBAL innodb_buffer_pool_size = 1073741824;` and `SET GLOBAL table_open_cache = 8192;`. The exact shell history was not kept; the values are the ones the run's `SHOW VARIABLES` snapshots recorded. `open_files_limit = 32270` is the container's observed default, not tuned. `table_definition_cache` and all other variables were not recorded and are `UNVERIFIED` (assumed image defaults). Because the buffer pool and table cache changed mid-run, the provisioning timings across phases are **not a controlled comparison**: sites, batch sizes and table counts differ between phases.

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

**Provisioning finding (clone path only; see Scope and limits, item 1):** Even with tuned MariaDB (`1 GiB` buffer pool, `8192` table cache), synchronous logical SQL cloning takes `~54–56s` per site (`~31s` wall at 2 workers). Customer-facing onboarding cannot run `bench new-site` or logical SQL restore inline; `PLT-003` should consider claiming from a **pre-warmed pool of idle tenant sites** replenished asynchronously in the background (or via `mariabackup`/CoW snapshots). The "sub-second assignment" is a design goal and is `UNVERIFIED`; no pool was built or measured here, and `ERP-003`'s real per-tenant setup time is not measured.

## 2. 50-Tenant Isolation & Cold-Cache Warming

- **Per-site MariaDB credential isolation:** Cross-tenant `SELECT` from `load-001.localhost` DB user against `load-050.localhost` `tabUser` failed cleanly with MariaDB `errno 1142` (`SELECT command denied`). This is the only real isolation observation in this spike, and it covers one site pair (first and last), not all `2,450` ordered pairs.
- **Per-site secrets & API key generation (`__Auth` Fernet encryption):** Seeding unique `Administrator` API keys/secrets across all 50 sites completed in `58.67s`.
- **Sequential 50-site HTTP/Redis warm (`50/50` HTTP `200`):**
  - `GET /api/method/ping`: mean `102.54 ms`, p50 `99.80 ms`, p95 `125.10 ms`, max `147.05 ms`
  - Authenticated `GET /api/method/frappe.auth.get_logged_user`: mean `53.80 ms`, p50 `47.30 ms`, p95 `77.49 ms`, max `142.96 ms`

## 3. Concurrent Load Results (50 Tenants, `c = 10, 25, 50, 100`)

Four waves of **250 requests each** (`1,000` total requests) spread across all 50 sites (`40%` `ping`, `40%` authenticated `get_logged_user`, `20%` authenticated `POST /api/resource/ToDo` carrying a unique per-request tenant tag) with `innodb_flush_log_at_trx_commit = 1`.

**What the response checks do and do not prove.** The column below was named "Isolation Mismatches" in the first draft of this report; that name overclaimed and is withdrawn. The in-wave checks cannot detect a request served by the wrong site: `ping` is unauthenticated and always passes, `get_logged_user` returns `Administrator` on every site, and the `ToDo` response echoes the request body. The column therefore counts only malformed or failed responses (it is `response_check_failures` in the runner JSON). The only weak routing signal is that each site's own API token was accepted. **The live run did not do a post-run cross-check of per-site ToDo rows**, so cross-tenant row placement in this run is **not verified** by this spike. The runner now includes `verify_tag_isolation` (reads each site's ToDo back with that site's token and asserts each written tag exists in its own site only; covered by offline tests that include a wrong-site case), but it has **not been run live yet**. Run it before citing any isolation result from this spike; `SEC-004` remains the isolation proof.

| Concurrency | Throughput (RPS) | HTTP 200 / Total | Response check failures (not an isolation signal) | Overall p50 (ms) | Overall p95 (ms) | Overall p99 (ms) | Overall Max (ms) | Write `ToDo` p50 / p95 (ms) |
|---|---|---|---|---|---|---|---|---|
| `c=10` | `39.66` | `250 / 250` (`100%`) | `0` | `122.44` | `979.91` | `1,210.03` | `1,306.25` | `596.84` / `1,207.18` |
| `c=25` | `79.53` | `250 / 250` (`100%`) | `0` | `266.07` | `614.40` | `956.06` | `1,131.17` | `428.80` / `970.97` |
| `c=50` | **`93.40`** | `250 / 250` (`100%`) | `0` | `434.80` | `736.93` | `812.66` | `1,117.32` | `546.23` / `822.87` |
| `c=100` | `90.07` | `250 / 250` (`100%`) | `0` | `876.27` | `1,434.06` | `1,497.95` | `1,699.03` | `927.10` / `1,491.58` |

Key observations:
1. **Zero HTTP errors:** All `1,000` concurrent multi-tenant requests returned `200 OK` with `0` timeouts and `0` malformed responses. This says nothing about cross-tenant leaks (see above).
2. **Thread-pool saturation knee at `~93 RPS` (`c=50 -> c=100`), on unrecorded hardware (Scope and limits, item 3):** With `workers=2 --threads=4` (`8` worker threads), throughput plateaus at `~90–93 RPS` above `c=50`; pushing concurrency from `50` to `100` doubles p50 (`434.80 ms -> 876.27 ms`) and p95 (`736.93 ms -> 1,434.06 ms`) which is consistent with Gunicorn queue wait (not separately measured), while `Max_used_connections` on MariaDB remained flat at **`17`** (`11.3%` of `151`).
3. **First-wave (`c=10`) cold table warmup effect (hypothesis, not isolated):** `c=10` had higher `ToDo` write p95 (`1,207 ms`) than `c=25` (`971 ms`), plausibly because the first write wave populated InnoDB buffer pool pages and `tabToDo` table handles across all 50 databases (`mariadb-1` RSS rose `+413 MiB` during `c=10`). Wave order and concurrency are confounded; no wave was repeated.

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

1. **Leading suspect — MariaDB memory and `table_open_cache` churn (hypothesis; no controlled A/B on request latency was run):**
   - `50` sites × `852` tables = `42,600` InnoDB tables. With minimal customer rows, `mariadb-1` RSS reached **`7.10 GiB`** once all 50 sites were active. That total includes the configured **`1 GiB` InnoDB buffer pool**, the InnoDB data-dictionary cache for the `42,600` tables, and the `8,192` open table handles. The data cannot separate these components, so **no per-site memory cost is derived** from it. (The first draft's "`~145 MiB` per empty site" divided total RSS by site count and is withdrawn: it mostly reflects the fixed buffer pool and the dictionary cache, and the buffer pool also changed between the `17`-DB and `50`-DB rows.) A true marginal cost per site is `UNVERIFIED` and needs a run that varies site count with the pool fixed.
   - Because `table_open_cache` (`8,192`) is smaller than `42,600` total tables, cross-site bursts evict and reopen tables: `Opened_tables` rose by `~43,000` during the `c=10` wave (`567,545 -> 610,788`). Whether this churn is what limits latency or throughput is not shown by this run.
2. **Python app-server (`engine-1`) memory did not look like the limit in this run:**
   - Each Gunicorn worker grew by only **`+26 MiB`** (`115.4 MiB -> 141.5 MiB`, i.e., `~1.05 MiB` per active site across 2 workers) after exercising all 50 sites.
3. **Redis cache footprint is modest (`~0.47 MiB` / `~29` keys per active site):**
   - `25.01 MiB` total across 50 warm sites (`0` evictions).

## 5. Recommendations for `PLT-003`, `INF-010`, and Bench Defaults

**Every figure in this section is an `UNVERIFIED` hypothesis**, extrapolated from empty cloned sites, one run, a `1 GiB` buffer pool, `1,000` requests and unrecorded host hardware (Scope and limits). None has an external source. Treat them as inputs for a proper sizing test, not as sizing guidance.

1. **Shard MariaDB at roughly 50-100 active tenants per DB node (`INF-010`) (`UNVERIFIED`).**
   - Observed: `42,600` tables and `7.10 GiB` RSS at `1 GiB` buffer pool for `50` empty sites. The hypothesis that a `16-32 GiB` node holds `50-100` real SMB tenants and that `100` is a safe ceiling is not measured: the per-site marginal cost, real data growth and busy working sets were not tested.
2. **MariaDB sizing for `INF-010` (`UNVERIFIED`).**
   - Hypothesis to test: `table_open_cache` near the total table count (the draft suggested `>= 32768`, with `open_files_limit >= 131072` and `table_definition_cache >= 16384`), and `innodb_buffer_pool_size` at `40-50%` of node RAM. These numbers are starting points for a sizing test, not results; they were never applied or measured in this run (the run used `8192` and `1 GiB`).
   - Keep `infra/dev/docker/my.cnf` light for developer laptops; the spike settings live in the opt-in [my.load-spike.cnf](../../infra/dev/docker/my.load-spike.cnf).
3. **Pre-warmed site pool for onboarding (`PLT-003`) (design direction, not measured).**
   - Measured: cold `bench new-site` `~240s`; tuned SQL clone `~54-56s` per site. Running either inline in a signup request looks unacceptable; the pool itself, its claim latency and `ERP-003`'s real setup time are `UNVERIFIED`.
4. **Gunicorn scaling (`INF-010`) (`UNVERIFIED`).**
   - Observed: `2` workers x `4` threads saturated near `~93 RPS` on unrecorded hardware. The `2 * cores + 1` worker rule is a common heuristic, not tested here; `QA-013` should measure async queue, report and ZATCA workloads.

## 6. Follow-ups before this report is used for sizing

- Run `verify_tag_isolation` live (it is wired into the runner as `tag_isolation_check`) and record the result; keep `SEC-004` as the isolation proof.
- Re-run with the `host` block recorded, and repeat waves to get variance.
- Measure provisioning through the real `ERP-003` path and compare with the clone numbers.
- Vary site count with the buffer pool fixed to get a real per-site memory cost.
