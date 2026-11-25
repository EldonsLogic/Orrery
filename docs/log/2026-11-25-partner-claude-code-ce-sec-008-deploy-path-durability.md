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

## Review round 1 (GPT-6.2 Sol at 56b00a23: changes required; 4 High, 4 Medium, 1 Low)
- Fixed:
  - non-DDL deployments (workflow, report, property setter) no longer need a DDL baseline;
  - caller ids that could collide with evidence keys are rejected, and rollback, lookups and finalizers act on main rows only;
  - a fresh read view is taken after the locks;
  - provenance is computed, and a restarted deployment always ends in RECOVERY_REQUIRED;
  - lookup row shapes are strict and read failures are typed;
  - a site-scoped idempotency lock, with `already_recorded` replaying the stored outcome;
  - stable reason codes, with exception text in internal logs only;
  - timeout validation at the RPC boundary, with a re-read on the dispatching session;
  - a stateful live mock.
- Red then green: the new `test_ce_sec_008_review_fixes.py` went from 69 failed and 16 passed to all passing. The two CE-SEC-008 files now give 77 passed with 76 subtests.
- Full suite: 1591 passed, 86 skipped, 0 failed.
- Follow-ups added to PLAN:
  - CE-SEC-009: a locked recovery entry point (needs an ADR).
  - CE-SEC-010: a dedicated journal table with a unique idempotency index (needs an ADR).
- Other follow-ups:
  - Adapter lane, part 2: in `frappe_backend.py`, the decimal backend must set the timeout before the intent. The workflow, report and property-setter engines need the idempotency lock and a fresh read view.
  - A bench proof with two MariaDB sessions.

## Review round 2 (GPT-6.2 Sol at ea12c1f1: changes required; 2 High, 3 Medium, 6 partly resolved)
- Fixed:
  - N1: the fresh read view no longer commits; it refuses over pending caller writes and otherwise rolls back a read-only transaction.
  - N2: locks fold site, doctype and key by case and trailing spaces, matching the column collation; new ids and keys must be canonical ASCII.
  - N3: both locks are acquired in one try/finally; release is verified, and a failed release discards the session.
  - N4: new ids are limited to 100 characters so derived keys fit; existing longer ids still look up and revert.
  - N5: the timeout is rechecked before the Custom Field insert, and pending writes are rolled back when no DDL was sent.
  - Round 1 remainders: the main-row filter on the internal lookup; an ordinary revert refused while a deployment is on hold (DEPLOYMENT_ON_HOLD); strict outcome objects; `revision_unavailable`.
- Red to green: the two CE-SEC-008 files went from 37 failed and 86 passed to 99 passed with 103 subtests.
- Full suite: 1613 passed, 86 skipped, 0 failed.
- UNVERIFIED: the Frappe 15 attribute name `transaction_writes`.
- Follow-up added to PLAN: CE-SEC-011, the adapter lane, bringing the non-DDL engines and the decimal backend onto the same lock discipline.

## Review round 3 (GPT-6.2 Sol at 510fcfb9: changes required; 1 High, 3 Medium; N3 and N4 fixed)
- Fixed:
  - The fresh read view refuses a write counter that is missing, invalid or non-zero, with no commit fallback. A dedicated connection is follow-up work in CE-SEC-011.
  - The site identity comes from the resolved site, never from caller input. Anything else is refused as `SITE_MISMATCH` or `INVALID_SITE_ID`.
  - A failed rollback discards the session and returns RECOVERY_REQUIRED (`session_discarded`), so the PREPARED hold stays.
  - The revert hold check runs only after authorisation. Moving it under the target lock is follow-up work in CE-SEC-011.
- Red then green: the two CE-SEC-008 files went from 21 failed and 103 passed to 124 passed, with 118 subtests.
- Full suite: 1624 passed, 86 skipped, 0 failed.
- The CE-SEC-011 row text now includes the dedicated connection and the locked hold check.

## Tokens or cost
Unknown.

## Next step
Cross-model review of this PR (Tier 3). Then CE-SEC-008 part 2 (the adapter deployment-id counter), after #310 and #312 merge.
