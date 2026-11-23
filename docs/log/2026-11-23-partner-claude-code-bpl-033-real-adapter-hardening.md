# Session log: bpl-033-real-adapter-hardening

Date: 2026-11-23
Author: partner
Tool and model: claude-code
Plan IDs: BPL-033

## Summary
First slice of `BPL-033` (PR #150 follow-ups), test first, no ledger or valuation logic touched. Engine: a failed write of the tenant-database state copy at finalize is no longer swallowed (the operation ends `recovery_required`, visible in the outcome, audit result and event), and the durable journal now lists a step only after it took effect. Backend: location steps dispatch on the Blueprint kind (unknown kind refused, branch and department an explicit no-op, a branch disable never reaches a Warehouse), and a read-only `check_ready` runs before the first step so a site that cannot take the artifact fails clean. `BPL-033` stays `todo` (second slice and bench work remain).

## Files touched
- apps/engine/change_engine/change_engine/adapter/engine.py: `_execute_all` journals after `_exec` succeeds and fails closed when the journal write fails; calls `check_ready` before `save_prepare_intent`; `_run` finalize writes the state copy inside the finalize transaction (after the lease check) and escalates a failure to `recovery_required`
- apps/engine/change_engine/change_engine/adapter/frappe_backend.py: `LOCATION_KINDS`, `_location_kind`, kind-aware `location.upsert` and `location.disable`, `check_ready`
- apps/engine/change_engine/change_engine/tests/test_bpl_033_engine_hardening.py (new): 8 tests, journal order, persistence failure, readiness hook
- apps/engine/change_engine/change_engine/tests/test_bpl_033_location_hardening.py (new): 13 tests on a fake engine
- apps/engine/change_engine/change_engine/tests/test_erp_026_pr126_review_fixes.py: one test moved its lease-expiry seam from the journal write to the ownership check, because the journal write now follows the step
- .github/workflows/tests.yml: step for the two new test files

## Decisions
- Journal design (contract 15.1: "a step that failed before taking effect is not listed"; phases are only `execute` and `compensate`): the `execute` entry is appended after the step took effect, not as a "pending then confirmed" pair (a `pending` phase would appear in `execution_journal()` and break the contract). The in-memory journal still marks the step executed before the durable write, so a journal write that fails after the effect ends `recovery_required` (the step is never reported as clean). A crash between the step and its journal entry leaves the operation to lease recovery, which already ends `recovery_required` (ADR-0028); no new window, since recovery never trusted the journal to decide that.
- State persistence: the write happens inside the finalize transaction, after `idem_complete` proved the lease, so a worker that lost its lease writes nothing. On failure the transaction rolls back and a second one stores `recovery_required` (stage `finalize`, event `blueprint.apply_failed`, audit result `recovery_required`), then a best-effort write keeps the tenant-database copy from claiming a ready site. This applies to every outcome, including no-effect ones (`rejected`, `already_applied`, `failed_clean`): fail closed was chosen over splitting the cases.
- Locations: the `location.disable` of a step without a definition (no kind) keeps the company-scoped Warehouse lookup, because the engine does not pass the kind to the backend; every compensation step carries its definition. Branch and department remain engine no-ops until open question 11 in `contracts/engine-adapter.md` (location elements: configuration or business records) is decided; not decided here.
- No ADR needed (no auth, tenancy, contract or compliance change).

## Verification
- New tests first: 7 engine and 8 backend tests failed before the fix, for the intended reasons; 21 pass after.
- `PYTHONPATH=apps/engine/change_engine pytest`: both new files plus BPL-027 offline (5 passed, rest skipped without a bench), BPL-007, BPL-008, BPL-012, ERP-012, ERP-026 (4 files), SEC-022 and BPL-032 (5 files), ERP-023, ERP-029, ERP-027 (2 files) all pass; CE-SEC-003, SEC-004, API deployment and caller-roles suites pass with `PYTHONPATH=apps/engine/change_engine:.` (96 passed).
- Conformance suite (`services/blueprint/tests/adapter`) 208 passed under `make_harness` and 208 under `make_frappe_harness`.

## Left for the next slice (not done here)
- Live read-back beyond `test_04` (non-warehouse locations, company and compliance settings, approvals, components, relations, numbering) and `sync_members` plus `execute_as_caller` against the bench site: needs the real bench; CI's real-bench job runs live tests on push.
- Re-run the live bench on the current head (the last run predates the `~` path edits and everything since).
- `stock_on_hand` binding: the report has no entity in the Blueprint and `_deploy_report` falls back to `sales_order`. Neither `contracts/engine-mapping.md` nor the mapping file defines a binding, so it is left (needs a mapping decision, then a fail-closed refusal or an explicit doctype).
- `attachment` support: `contracts/blueprint.schema.json` allows it, the mapping has no engine type for it (`mapping.py`, the mapper being edited by `BPL-031`). Left until the mapping row exists.
- `sync_members` still writes the state copy after its store transaction commits; a failure there raises to the caller (not swallowed) but leaves members and version committed. Could move inside the transaction like finalize; not changed (not in the review finding).
- What the bench must prove: `check_ready` against a real multi-company and zero-company site (warehouse refusal before `settings.set`), kind-aware disable on the real Warehouse table, and a real tenant-database failure at finalize ending `recovery_required`.

## Tokens or cost
Unknown.

## Next step
Second slice of `BPL-033`: live read-back and caller-permission checks on the bench, bench re-run on the current head, then `stock_on_hand` and `attachment` once the mapping defines them (after `BPL-031`).
