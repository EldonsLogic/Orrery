# Change engine

Status: draft
Owner: eldon

The "change engine" is a module, adapted from a partner-built prototype, that implements guarded configuration changes on Frappe. It is the apply / preview / rollback / audit / policy layer of Part 2, living at `apps/engine/change_engine/` (see its `README.md` and `PROVENANCE.md`). It is not a separate project and carries none of the prototype's name or branding. ADR-0013.

**Status after import:** the deterministic guarded-apply code is in; the prototype's LLM planner, Desk sidebar, LLM settings screen, mock ERP seeder and demo workspaces were not imported because they conflict with the architecture (AI work lives in separate services behind the gateway; the product UI is the one chat). Standalone unit tests pass and `CE-SEC-005` adds live pinned-bench CI (`.github/workflows/real-bench.yml`, `infra/dev/docker/run_real_bench_ci.py`, `test_ce_sec_005_real_bench.py`) exercising `plan`/`apply`/`rollback`/policy and negative security regressions against real Frappe v15, ERPNext, HRMS, MariaDB 11.4, and Redis.

## What it does (prototype)
Preview of changes, a pre-execution DDL plan gate, an audited six-stage deploy, soft-quarantine rollback, declarative workflows and reports, and runtime policy enforcement.

## Mapping to Part 2 ([spec 02](../specs/02-blueprint-and-library.md))
| Prototype capability | Role in the platform | Stays / replaced |
|---|---|---|
| Preview | Renders the plan for a Blueprint diff (owner-facing explanation built on top) | Stays; explanation layer is new |
| Pre-execution DDL plan gate | Implements adapter `plan` with risk flags and destructive-op detection | Stays |
| Six-stage audited deploy | Implements adapter `apply`; each stage emits events | Stays; events aligned to [events.md](../../contracts/events.md) |
| Soft-quarantine rollback | Implements `rollback` with data-preserving inverses | Stays |
| Declarative workflows and reports | Target of the compiler for workflow and report sections | Stays; input format replaced by the compiled output of the Blueprint schema |
| Runtime policy enforcement | Enforcement of Blueprint roles, scopes, approval rules at runtime | Stays; **storage and authorisation replaced** (CE-SEC-003) |
| Prototype's own request/LLM endpoints and settings | Replaced by the Tool API gateway and AI gateway | Replaced |
| Prototype's input schema | Replaced by the Blueprint schema compiler output | Replaced |

## Known issues (security; fix before any real use)
| ID | Issue | Required fix |
|---|---|---|
| CE-SEC-001 | Caller-supplied roles are accepted from request kwargs on whitelisted endpoints | Remove all role/identity parameters from endpoints. Derive identity and roles server-side from the authenticated session; ignore and reject client-sent roles. Add tests that attempt role injection |
| CE-SEC-002 | Role lookup falls back to System Manager on error (fail-open) | Fail closed: on any lookup error, deny and log. Remove every default-to-admin path. Test with a broken role store |
| CE-SEC-003 | Runtime-policy registration has no permission check; policies are held in process memory (not persisted, per-process, not per-site) | Require an explicit admin permission to register; persist policies per site in the database with revision and audit; load at worker start; verify consistency across workers; policies derive from the approved Blueprint revision, not ad hoc registration |
| CE-SEC-004 | The LLM test-connection endpoint accepts a client-supplied API key and base URL | Remove the endpoint from tenant-facing surfaces. Provider keys and base URLs live only in the gateway's vault configuration; any test is an internal, admin-only action using stored config; block SSRF (no arbitrary URLs) |
| CE-SEC-005 | CI runs mocks, not a real Frappe bench | CI must stand up a real bench with the pinned version set and run integration tests for plan/apply/rollback/policy, including negative security tests. Mocks only for unit tests |
Also required on import: add a LICENSE file (decision on licence recorded in NOTICE.md and an ADR; GPL implications of loading into Frappe processes considered, see [engine-adapter](engine-adapter.md)).

## Security fix status
| ID | Status | Evidence |
|---|---|---|
| CE-SEC-001 | Fixed in import | Inside Frappe, roles come only from the session; client `user_roles`/`caller_roles` ignored. Test: `test_caller_roles.py` |
| CE-SEC-002 | Fixed in merged PR #153 | Rollback role lookup and invalid or missing session contexts fail closed. Tests: `test_caller_roles.py` and live HTTP regressions. Sibling role defaults and proposal authorization remain tracked follow-ups from that PR's independent review. |
| CE-SEC-003 | Implemented | Policy writes require an authorised session role. The policy store persists site-scoped revisions and audit records in MariaDB. |
| CE-SEC-004 | Fixed in import | LLM test-connection and config endpoints removed. Provider keys live only in the gateway |
| CE-SEC-005 | In review | Real bench CI workflow `.github/workflows/real-bench.yml` and orchestrator `infra/dev/docker/run_real_bench_ci.py` run `test_ce_sec_005_real_bench.py` and `test_ce_sec_005_live_http.py` against pinned Frappe `v15.126.0`, ERPNext `v15.124.5`, HRMS `v15.64.8`, MariaDB `11.4`, and Redis `7.2.7` |

## Import checklist
1. Module at `apps/engine/change_engine/`, no old name in code, docs, DocTypes or CI (checked by `scripts/check_repo_hygiene.py`). Done.
2. CE-SEC-001 through CE-SEC-004 have regression tests. CE-SEC-005 tracks live-bench verification and acceptance.
3. Align deploy-stage events to the event contract; add `tenant_id` and audit fields.
4. Wire to the compiler through the adapter interface (the module has no LLM or request-planning paths).
5. Gate G0 requires the known bugs fixed (see [GATES](../GATES.md)).
6. Security review by the partner (cross-model review).

## Open questions
1. Licence for the module given it loads into the GPL engine process.
2. Whether quarantine retention windows are per tenant or platform defaults.
3. Which prototype tests are worth keeping once CI uses a real bench.

Plan IDs: BPL (module), SEC (CE-SEC items), QA (bench CI), GOV (rename gate).
