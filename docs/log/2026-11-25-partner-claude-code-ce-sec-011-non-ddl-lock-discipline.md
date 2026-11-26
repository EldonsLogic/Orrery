# Session log: ce-sec-011-non-ddl-lock-discipline

Date: 2026-11-25
Author: partner
Tool and model: claude-code / claude-opus-5-5 (coordinator); implementation by a Claude Sonnet 5.5 child, test-first
Plan IDs: CE-SEC-011

## Summary
CE-SEC-011 slice 1: the property-setter, workflow and report engines now follow the single-field path's lock discipline. Their raw exception text is replaced by stable codes, the revert hold is checked under the target lock, and custom `site_map` tenants resolve through the backend's resolver. This is part of the partner's Wave 2 (see the 2026-11-25 partner sprint log).

## Files touched
All paths are under `apps/engine/change_engine/change_engine/`.
- `guarded_apply/schema_reconciler.py`:
  - New shared helpers: `acquire_scoped_locks`, `release_scoped_locks`, `begin_fresh_read_view_checked`, `set_lock_wait_timeout_checked`, `blocked_response`, `engine_refusal`.
  - They reuse `_release_checked`, `_discard_session` and the lock-key makers.
  - `execute_single_field_deployment` is unchanged.
- `guarded_apply/property_setter_engine.py`, `workflow_engine.py`, `report_engine.py`:
  - Locks are taken in order: idempotency lock, then target lock.
  - A fresh read view is taken after the locks.
  - A lookup failure blocks the deployment.
  - The timeout is set and verified before the intent.
  - Every release is verified.
  - Stable codes replace raw text: `audit_prepare_failed`, `apply_failed`, `revision_unavailable`, `invalid_*_payload` and `finalization_failed`.
- `guarded_apply/rollback_engine.py`:
  - The revert takes the target lock, opens a fresh view and re-reads the record.
  - It refuses a hold under the lock.
  - It returns `ALREADY_*` if a concurrent revert finished first.
- `api/endpoints.py` and `adapter/frappe_backend.py`:
  - New `FrappeSiteResolver.tenant_of(site)`; the adapter takes a `site_resolver`.
  - `_tenant_of_site`, `_read_site_ids` and `_resolve_site_id` use the resolver.
  - The revert no longer checks the hold outside the lock.
  - The coordinator gave the three JSON-parse refusals fixed text and `reason_code: invalid_json_payload`.
- New `tests/test_ce_sec_011_non_ddl_lock_discipline.py`, 31 tests; it imports the CE-SEC-008 fakes.
- `tests/test_sec_022_bpl_032_roles.py`: the coordinator changed one assertion, because the workflow engine now takes two locks (idempotency, then target).
- `docs/PLAN.md`: the CE-SEC-011 text now names what slice 1 delivered and what remains (the dedicated connection). The keyed MAC moves to ADR-0070's follow-ups.

## Evidence
- New test file: 57 failed before the fix, then green.
- Full change-engine suite: 1809 passed, 86 skipped, 0 failed. The baseline was 1778 passed.

## Not covered
- `ZoneSafetyViolation` text still echoes the caller's own input. That is the caller's own data, so nothing is disclosed.
- The field path is not folded onto the new helpers, to avoid touching merged Tier 3 code.

## Review round 1 (Gemini 4 Argon at 9005fd47: changes required; 1 High, 2 Medium, 1 Low)
- Fixed:
  - **High (regression).** `_deploy_workflow` inserted the Workflow Action Master uncommitted before the deployment, so the fresh view refused every workflow that creates an action. The engine now creates actions with `ensure_workflow_action`, after Stage 3 PREPARED, under the locks and inside the apply's try.
  - **Medium.** The report and workflow validators return fixed messages (`invalid_report_definition`, `invalid_workflow_state_machine`).
  - **Medium.** Steps 6 and 7 of the workflow engine run inside the apply's try. `settle_apply` rolls back uncommitted apply writes, and a failed rollback or a discarded session holds the deployment as RECOVERY_REQUIRED. A deactivation that was already committed and is followed by a failed apply is held, not marked FAILED_CLEAN.
  - **Low.** `FrappeSiteResolver` validates `site_map` (tenant-id keys, string values, no collision with another tenant's default site). A resolver error gives `site_unresolvable`.
- Not changed: the property setter's second write (`reqd=0`) after a successful main property is still swallowed. It is outside this slice.
- Red then green: 37 failed and 40 passed, then all pass. Full suite: 1827 passed, 86 skipped, 0 failed.

## Review round 2 (Gemini 4 Argon at c61972ef): items 1, 2 and 4 resolved, item 3 partly; one Medium fixed
- The property setter no longer swallows a failed second write (`reqd=0`) after the main property has committed. It sets `partial_apply`, `settle_apply(failed=True)` rolls back the uncommitted write, and the deployment is held as RECOVERY_REQUIRED, never APPLIED or FAILED_CLEAN. If the rollback fails, the session is discarded and nothing is finalized.
- Tests: `TestR5QuarantineSecondWriteFailureIsAHold` (4 tests; 3 failed before the fix, all pass after).
- Full suite: 1831 passed, 86 skipped, 0 failed.

## Eldon's security review at 4a6606b7 (2026-11-26): fixes
- Written by Claude Opus 5.5 (sub-agent, no git, confined to the #338 files and `tests.yml`); the coordinator re-ran the suite.
- R1: `python-tests` was red because the workflow's unmapped-test loop flagged the CE-SEC-011 test file; both CE-SEC-011 test files are now on the CE-SEC-008 run line in `.github/workflows/tests.yml` (one line).
- R2: the six non-DDL adapter writes (`apply_property_setter`, `ensure_workflow_state`, `ensure_workflow_action`, `apply_workflow`, `set_workflow_active`, `apply_report`) go through `_require_guarded_write()`, which checks the session and the locks before the write and before the commit; a lost lock discards the session and holds the deployment (intent stays PREPARED). The reviewer's probe was reproduced first (workflow and report returned APPLIED with the locks dropped).
- R3: refusal, not a resolver. The site map lives only in `FrappeRuntimeBackend`, so an RPC-built live adapter now asks the site database for any tenant identity other than the one it computed (a site-state row, or audit rows under a tenant id) and refuses with `site_unresolvable` if it finds one or the read fails. The revert RPC already takes its site from the record (test proves `recovery_hold` on a mapped site). Remaining gap: a mapped site with no state row and no tenant-id audit row still runs under its host name; recorded as CE-SEC-011 slice 2.
- Lows: the target is read back before reporting FAILED_CLEAN (a changed or unreadable target gives RECOVERY_REQUIRED, `apply_failed`); the revert refuses `engine_unavailable` when the caller has pending writes, so its CREATE TABLE never commits them; tests for the revert site and doctype checks and the ALREADY_* replays.
- New row CE-SEC-016 (the review's "not from this PR" item, plus the three writes still without a lock check). Q-658 and Q-659 were not used.
- Mutation check: 20 of 20 mutants killed. Full suite: 1853 passed, 86 skipped (was 1831).
- UNVERIFIED: the real-bench effect of the read-back SQL and of the revert change; real-bench test order where `test_ce_sec_005_real_bench.py` test_04 maps a tenant onto its site (later admin RPC applies there are refused; today those are staff calls, refused on roles first).
- Size: about 182 changed source lines plus a 522-line test file, over the 400-line guide; kept in one PR because the review asked for all three fixes before merge.

## Tokens or cost
Unknown.

## Next step
Gemini 4 Argon security review, then the PR (Tier 3). Slice 2 is the dedicated deployment connection; it waits for ADR-0070.
