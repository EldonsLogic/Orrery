# Session log: ce-sec-008-deploy-path-durability

Date: 2026-11-25
Author: partner
Tool and model: claude-code / claude-opus-5-5 (coordinator); implementation by a Claude Sonnet 5.5 child, test-first
Plan IDs: CE-SEC-008

## Summary
CE-SEC-008 part 1 fixes four durability defects in today's guarded deploy path, found in the #309 reviews.
- Durable baseline and statement evidence is written before any effect.
- Idempotency and recovery lookups fail closed on database errors.
- The lock-wait timeout is checked by reading it back.
- The Stage 3 intent is inserted strictly.

Part 2 is the per-process deployment-id counter in the adapter; it is adapter-lane work and comes later. Coordination is in 2026-11-25-partner-claude-code-partner-sprint.md (PR #316).

## Files touched
All under `apps/engine/change_engine/change_engine/`:
- `api/endpoints.py`:
  - The baseline is committed with the intent in one transaction, before any DDL. It reuses the existing audit table as append-only `<dep>#evidence` rows, so there is no schema change.
  - `load_durable_evidence()` rebuilds the evidence after a restart.
  - A dispatch-intent row is written before each statement and a completed row after it, so a statement is never recorded as executed before it takes effect. Completion truth is the main row's Stage 6 status.
  - Lookups raise on database errors and on unparseable stored outcomes.
  - The lock-timeout setter validates its value, raises on failure and checks the read-back.
  - The Stage 3 intent is a plain INSERT. A duplicate raises `DeploymentIntentConflictError` (`binding_mismatch` or `already_recorded`) and leaves the older row untouched.
- `guarded_apply/schema_reconciler.py`:
  - A lookup failure gives `REJECTED` with `engine_unavailable`, and no intent is written.
  - The lock timeout is set and verified before the intent (`lock_timeout_not_effective`).
  - An intent conflict gives `REJECTED` with `intent_<reason>`.
- `adapter/simulated_frappe.py`, `tests/test_api_deployment.py`: the test doubles answer `SELECT @@SESSION.lock_wait_timeout` (3 lines and 2 lines). The coordinator applied these.
- `tests/test_ce_sec_008_deploy_path_durability.py`: new, 41 tests with 16 subtests. They cover:
  - crash boundaries
  - repeated identical requests
  - conflicting bindings
  - database outages
  - timeout read-back mismatch
  - restart from durable evidence
- `.github/workflows/tests.yml`: a new CI step for the new test file.

## Evidence
- Red before: the new file had 45 failing tests and 12 passing. The 12 cover behaviour that was already correct.
- Green after: the new file passes 41 tests.
- Full change-engine suite (`PYTHONPATH=apps/engine/change_engine uvx --with pyyaml --with jsonschema --with pydantic --with pymysql --with werkzeug --with hijridate pytest -q apps/engine/change_engine/change_engine/tests`):
  - before the change: 1514 passed, 86 skipped
  - after it, with the test-double patch: 1555 passed, 86 skipped, 0 failed
- Without the test-double patch, 108 tests in 8 files failed closed on the new read-back. That failure is expected.

## Decisions
- No new ADR: this implements ADR-0068 items 13, 15 and 18 (Proposed, PR #309) for today's path.
- Design call for review: a dispatched statement that left the live schema equal to the baseline counts as "nothing executed" (ADR-0068 item 16), so `FAILED_CLEAN` stays for failed ALTERs.

## Open follow-ups
- `frappe_backend._execute_six_stage_field` still sets the timeout after the intent, and its lookups now raise raw exceptions. Both are adapter lane (part 2), blocked by the open PRs #310 and #312.
- `get_deployment_record` and `mark_recovery_required` still swallow database errors.
- The workflow, report and property-setter engines call the same lookups, so they now raise on a database outage. That is fail closed, but they have no clean refusal yet.
- The new test file has 734 lines, above the ~500-line guideline.

## Tokens or cost
Unknown.

## Next step
Cross-model review of this PR (Tier 3). Then CE-SEC-008 part 2 (the adapter deployment-id counter), after #310 and #312 merge.
