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

## Tokens or cost
Unknown.

## Next step
Gemini 4 Argon security review, then the PR (Tier 3). Slice 2 is the dedicated deployment connection; it waits for ADR-0070.
