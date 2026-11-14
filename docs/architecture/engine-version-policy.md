# Engine version pin and upgrade policy

Status: draft
Owner: partner
Plan ID: ERP-004

This document defines how the platform pins its ERP engine stack (Frappe, ERPNext, HRMS, database, cache, base image) and promotes a newer version set safely. Every tenant runs on one shared pinned set behind the [engine adapter](engine-adapter.md) ([ADR-0002](../decisions/ADR-0002-seed-engine-frappe-erpnext.md), [ADR-0008](../decisions/ADR-0008-no-client-specific-code.md)).

## 1. Current pinned set

Values below are copied from [Dockerfile](../../infra/dev/docker/Dockerfile), [docker-compose.dev.yml](../../infra/dev/docker/docker-compose.dev.yml), [verify_dev_bench.py](../../infra/dev/docker/verify_dev_bench.py), [apps/engine/README.md](../../apps/engine/README.md), [licence-register.md](../legal/licence-register.md), and [NOTICE.md](../../NOTICE.md):

| Component | Exact pin in repo | Licence | Verification status |
|---|---|---|---|
| Engine base OCI image | `frappe/erpnext@sha256:6e016c0fc3aec5b32c14ff7c2ac97523cc864748c83ce75197779b8fe5a665a8` | Mixed (MIT + GPL v3.0) | Clean `--no-cache` build on `linux/amd64`; other architectures `UNVERIFIED` |
| Frappe Framework | `15.126.0` (`v15.126.0`) | MIT | Version verified on synthetic site; packaged git commit inside base image `UNVERIFIED` |
| ERPNext | `15.124.5` (`v15.124.5`), metadata commit `e5cde8c4b9e3f7f567a92ca3e65fd411402b89ce` | GNU GPL v3.0 | Version verified on synthetic site |
| Frappe HRMS | `v15.64.8` (`15.64.8`), `HRMS_COMMIT=186900a6e3db4e6f927f1ee20df745bbb082638a` | GNU GPL v3.0 | Commit verified at build and runtime |
| Change engine | `0.1.0` (`apps/engine/change_engine/`, adapted from `f0ce226dd8d050fbc947caf50657e651e01792b8`) | Proprietary / Founder contribution | Mounted read-write; version verified on synthetic site |
| MariaDB | `mariadb:10.6@sha256:f1c56f035ed268a0d7c2c2e06dc879f6319b997cb434cf822a4cfd72a7aa184d` | GNU GPL v2.0 | **Past Community EOL (`2026-07-06`)**; runtime version check not in `verify_dev_bench.py` |
| Redis (`redis-cache`, `redis-queue`) | `redis:7.2.7-alpine@sha256:ddd16a9b1575a774c7e62956be8daa1de5b32cfb5c25b7a216aefed8e0919f9b` | BSD-3-Clause source; counsel review pending (`Q-15`) | `PING` verified; container contents/licence reading `UNVERIFIED` |
| Python and Node runtimes | Inherited from base image | PSF / MIT | Not explicitly pinned or checked in repo (`UNVERIFIED`) |
| ERPGulf ZATCA | `Planned` (`CMP-002`) | MIT | Not yet pinned or built |

Additional `UNVERIFIED` bench state: on `2026-11-14`, `docker compose build --no-cache engine` succeeded cleanly, while `verify_dev_bench.py` passed against an existing synthetic site created on `2026-11-11`. Running `bench new-site` from a freshly rebuilt image and running real-tenant production workloads remain `UNVERIFIED`.

## 2. Pin rules

- **Immutability:** Every OCI base and service image must resolve by `@sha256:` digest (human-readable tag retained alongside for clarity). Every upstream app cloned outside the base image must pin a release tag and verify its exact 40-character commit SHA at build time (`HRMS_COMMIT`). Local apps (`change_engine` and future `core`, `compliance`, `components`) track repo HEAD and declare `__version__`.
- **Single source of truth:** Today, pins are duplicated across [Dockerfile](../../infra/dev/docker/Dockerfile), [docker-compose.dev.yml](../../infra/dev/docker/docker-compose.dev.yml), [verify_dev_bench.py](../../infra/dev/docker/verify_dev_bench.py), [licence-register.md](../legal/licence-register.md), and [NOTICE.md](../../NOTICE.md). **Proposed (`Q-26`):** consolidate all runtime pins into one machine-readable manifest read by Docker builds, Compose/IaC, tests, and verifiers so values cannot drift.
- **Automated build and verifier checks:** [test_dev_bench_pins.py](../../infra/dev/docker/tests/test_dev_bench_pins.py) enforces `@sha256:` resolution for `engine`, `mariadb`, `redis-cache`, and `redis-queue`. [test_hrms_build_pin.py](../../infra/dev/docker/tests/test_hrms_build_pin.py) verifies build failure on commit mismatch. [verify_dev_bench.py](../../infra/dev/docker/verify_dev_bench.py) checks live app versions, HRMS commit, and Redis `PONG` (gap: it does not yet assert MariaDB version, Python/Node versions, or `frappe`/`erpnext` commits).
- **Change authority:** Pins live in `partner`-owned `infra/` and `apps/engine/` paths ([ADR-0020](../decisions/ADR-0020-lane-guard.md)). Any pin change requires a PR reviewed by the other founder or a different model; changes touching auth, tenancy, contracts, or compliance require security review ([RULES](../RULES.md) rule 42).

## 3. Upstream facts with sources

All external facts below were checked on `2026-11-14`:

- **Frappe and ERPNext lifecycle:** Frappe supports two major versions at a time (~2.5–3 years each). `version-14` reached EOL on `2026-01-31`; `version-15` has planned EOL `End of 2027`; `version-16` has planned EOL `End of 2029`; `develop` is unsupported bleeding edge. Fixes are not auto-merged between branches and require separate backport PRs ([Supported-Versions.md](https://raw.githubusercontent.com/wiki/frappe/erpnext/Supported-Versions.md), accessed `2026-11-14`). Active `v16` releases exist (e.g., `v16.56.0` on `2026-11-10`; [Frappe releases](https://api.github.com/repos/frappe/frappe/releases?per_page=10), accessed `2026-11-14`). A fixed calendar patch cadence (weekly vs monthly) is `UNVERIFIED` in official release docs, though patches ship frequently via automated GitHub releases (`v15.126.1` on `2026-11-10`).
- **Python and runtime dependencies:** Frappe `version-15` requires `requires-python = ">=3.10,<3.15"` and the Python Redis client `redis~=4.5.5` (a client library pin, not a server version) ([Frappe v15 pyproject](https://raw.githubusercontent.com/frappe/frappe/version-15/pyproject.toml), accessed `2026-11-14`), and ERPNext `version-15` requires `frappe >=15.111.0,<16.0.0` ([ERPNext v15 pyproject](https://raw.githubusercontent.com/frappe/erpnext/version-15/pyproject.toml), accessed `2026-11-14`). Frappe `version-16` requires `requires-python = ">=3.14,<3.15"` ([Frappe v16 pyproject](https://raw.githubusercontent.com/frappe/frappe/version-16/pyproject.toml), accessed `2026-11-14`).
- **HRMS compatibility:** Frappe HR declares `required_apps = ["frappe/erpnext"]` ([HRMS v15 hooks](https://raw.githubusercontent.com/frappe/hrms/version-15/hrms/hooks.py), accessed `2026-11-14`) and must match Frappe and ERPNext's major branch; mismatched major branches halt migration ([HRMS branching wiki](https://raw.githubusercontent.com/wiki/frappe/hrms/Changes-to-branching-and-versioning.md), accessed `2026-11-14`). Exact intra-`v15` patch bounds between ERPNext and HRMS are `UNVERIFIED` except by testing the combined set together.
- **MariaDB support and `10.6` EOL:** **MariaDB Community Server `10.6` reached EOL on `2026-07-06`**. `10.6.28` (`2026-08-13`) was its final community release; there will be no `10.6.29` and no further community bug or security fixes. Maintained Community LTS branches are `10.11`, `11.4`, `11.8`, and `12.3`; MariaDB Foundation recommends moving `10.6` directly to `11.8` or `12.3` ([MariaDB Q3 2026 release and 10.6 EOL](https://mariadb.org/mariadb-server-12-3-11-8-11-4-and-10-11-q3-2026-maintenance-releases-and-goodbye-10-6/), accessed `2026-11-14`). Community LTS policy provides 3 years of binaries after GA plus 2 years source-only critical/security fixes, or 5 years of binaries up to `11.4` ([MariaDB maintenance policy](https://mariadb.org/about/#maintenance-policy), accessed `2026-11-14`). Exact EOL calendar dates for `10.11`, `11.4`, `11.8`, and `12.3` remain `UNVERIFIED` directly (`endoflife.date` timed out).
- **Redis support:** `7.2.x` has extended security support until `7.4` end of support, alongside `7.4.x` and `8.2.x`–`8.10.x`. Redis permits `7.2` users to apply security patches from `7.4+` under `BSD-3-Clause` ([Redis SECURITY.md](https://raw.githubusercontent.com/redis/redis/unstable/SECURITY.md), accessed `2026-11-14`). Exact calendar EOL date for `7.2` and Frappe `v15` minimum Redis server version remain `UNVERIFIED`.

## 4. Upgrade classes

| Class | Trigger | Who approves | Required evidence | Rollback path |
|---|---|---|---|---|
| **Patch within `v15`** (`v15.x.y -> v15.x.z`) | Upstream bug fixes, non-breaking dependency fixes, platform stability need | `partner` + PR review (other founder or cross-model) | Clean build, pin tests, `verify_dev_bench.py`, conformance + `ERP-014` + `CMP-008` + canary | Re-pin prior digest; snapshot restore or forward-fix per `ADR-0028` |
| **Minor / feature within `v15`** (schema or behaviour shift, or adopting ERPGulf ZATCA) | Required platform capability or dependency alignment | Both founders (`RULES 42` if contract/compliance shifts) | All Patch evidence + synthetic `bench migrate` + ZATCA sandbox (`CMP-004`) + Arabic/RTL PDF check | Pre-upgrade per-tenant DB + files restore |
| **Major (`v15 -> v16`)** | `v15` approaching EOL (`End of 2027`) or required runtime/Python upgrade | Both founders + formal ADR | Dedicated spike, full adapter/change-engine rewrite audit, backup/restore drill, staged fleet migration | Per-tenant snapshot restore before promotion; no mixed-major production fleet |
| **Dependency** (`MariaDB`, `Redis`, `Python`, `Node`) | Upstream EOL (immediate: MariaDB `10.6`), CVE, or Frappe prerequisite | `partner` + `eldon` if licence/cost/in-country hosting (`INF-001`) changes | Licence review (`LEG-006`), `mariadb-upgrade` / cache compatibility test, `ERP-014` + isolation suite (`SEC-004`) | Restore snapshot onto prior service digest before app schema divergence |
| **Security hotfix** | Upstream CVE / active exploit on exposed or tenant-isolation path | `partner` + expedited other-founder / cross-model check | Clean build, targeted exploit/regression check, `ERP-014` sanity, pre-hotfix snapshot | Gateway block/feature disable if fix breaks; snapshot restore if DB touched |

## 5. Upgrade procedure (gates, not dates)

No release advances to the next gate until the current gate passes and is logged ([GATES.md](../GATES.md)):

1. **Branch:** Open a dedicated branch naming the plan or security ID; never push to `main`.
2. **Pin and licence update:** Update image digests, `HRMS_COMMIT`, `verify_dev_bench.py` (or unified manifest), [licence-register.md](../legal/licence-register.md), and [NOTICE.md](../../NOTICE.md). Run `LEG-006` counsel review if a licence or boundary changed.
3. **Clean build and static checks:** Run `docker compose build --no-cache engine` and `test_dev_bench_pins.py`. Once `INF-006` and `SEC-007` exist, container image and Python/Node vulnerability scans must pass.
4. **Bench verifier:** Boot synthetic stack and pass `verify_dev_bench.py` (extended to assert MariaDB, Python, Node, and app git commits).
5. **Engine, adapter, and gateway conformance:** Pass real-bench change-engine CI (`CE-SEC-005`), adapter conformance (`BPL-025`/`BPL-027`), Phase-0 proof suite (`ERP-021`), cross-tenant isolation (`SEC-004`), gateway error/path parity (`PLT-024`), and invisibility crawl (`QA-016`).
6. **Compliance and deterministic finance regression:** Pass accounting and tax property tests (`ERP-014`), ZATCA Phase 2 regression suite (`CMP-008`, when built), and bilingual Arabic/RTL PDF print verification (`ERP-007`).
7. **Migration rehearsal:** Run `bench migrate` against cloned synthetic sites spanning supported Blueprint revisions; fail on any unguarded DDL error or data loss.
8. **Backup and restore proof:** Capture a full per-tenant DB + site-files snapshot and verify a timed restore to an isolated instance (`DAT-004`/`DAT-005`).
9. **Staged rollout:** Promote through `synthetic sandbox -> internal canary tenant -> small tenant batch -> fleet`, recording `engine.upgrade_canary_started` and `engine.upgrade_promoted` in the [event stream](../../contracts/events.md). Every active tenant finishes on the same pinned set.
10. **Halt and rollback criteria:** Halt rollout and emit `engine.upgrade_rolled_back` immediately on any failed `bench migrate`, ledger/tax assertion failure, ZATCA rejection spike, gateway 5xx rise, or engine-marker leak. Roll back by restoring pre-upgrade tenant snapshots or applying a verified forward repair ([ADR-0028](../decisions/ADR-0028-recoverable-journaled-change-apply.md) — DDL changes and external fiscal submissions cannot be undone cleanly by app-level inverse alone).

## 6. Security patch handling

- **Advisory monitoring:** Track [Frappe Security Advisories](https://github.com/frappe/frappe/security/advisories), [ERPNext Security Advisories](https://github.com/frappe/erpnext/security/advisories), [frappe.io/security](https://frappe.io/security) (all accessed `2026-11-14`), MariaDB and Redis security notices, GitHub Dependabot, plus planned `SEC-007` (SBOM) and `INF-006` (image scanning).
- **Maximum exposure rules (no calendar dates):**
  - **CRITICAL or actively exploited CVE** on a gateway-reachable, auth, or cross-tenant boundary blocks new tenant provisioning and non-security deploys until patched, blocked at the gateway (`PLT-024`), or formally risk-accepted by both founders.
  - **HIGH CVE** on an active engine or runtime path gates the next staging-to-production promotion until patched or mitigated.
  - **MEDIUM/LOW or unreachable CVEs** roll into the next scheduled patch train.
  - **Current breach of rule:** MariaDB `10.6` is already Community EOL and receives zero security fixes; it must be replaced before `G2` or production hosting (`INF-005`).
- **Emergency hotfix path:** Apply temporary gateway mitigation (`PLT-024`) first if an upstream fix is unavailable -> prepare minimal pin-bump PR -> pass Gate 3, Gate 4, `ERP-014`/`SEC-004` smoke, and per-tenant snapshot -> canary then fleet rollout -> log outcome with cross-model/other-founder review.

## 7. Interaction with existing rules

- **Engine invisible (`ADR-0016`):** Upgrades may change internal DocTypes or Desk responses. Every bump must leave gateway API routes, error shapes, cookies, headers, emails, and PDFs free of engine markers (`PLT-024`, `QA-016`).
- **No forks and no per-client code (`ADR-0008`, `RULES 20`):** We do not maintain private Frappe/ERPNext forks or leave individual customers on older engine pins. Temporary hotfixes stay minimal upstream-trackable pin bumps until upstream releases merge.
- **Deterministic rigid zone (`RULES 21`, `RULES 30`):** Ledger, tax, rounding, payroll maths, Hijri conversion, and ZATCA payloads stay deterministic code and block any bump whose regression tests fail (`ERP-014`, `CMP-008`).
- **Licence and SaaS boundary (`licence-register.md`, `NOTICE.md`, `LEG-006`):** Every bump re-confirms no `AGPL` dependency entered the image and updates both licence files in the same PR.

## 8. Open questions and founder decisions

- **Existing open items:** `Q-6` (real-workload proof on pinned `v15` set and move policy) and `Q-15` (Redis `7.2.x` licence reading vs Valkey) in [open-questions.md](../open-questions.md).
- **New decisions needed (added as `Q-25`..`Q-27` in [open-questions.md](../open-questions.md)):**
  - `Q-25`: Upgrade `mariadb:10.6` (EOL `2026-07-06`) to MariaDB `11.8` LTS or `10.11` LTS, and gate that compatibility test before `G2`/`INF-005`?
  - `Q-26`: Replace duplicated pins across Docker/Compose/verifier with one machine-readable manifest and extend `verify_dev_bench.py` to check MariaDB, Python, Node, and `frappe`/`erpnext` commits?
  - `Q-27`: Ratify the proposed gate-based security exposure rules and define the trigger rule for planning the Frappe `v15` (`End of 2027` EOL) to `v16` (Python `>=3.14`) upgrade?
