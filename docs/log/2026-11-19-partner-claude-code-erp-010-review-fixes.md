# Session log: erp-010-review-fixes

Date: 2026-11-19
Author: partner
Tool and model: claude-code / claude-sonnet-5-5
Plan IDs: ERP-010

## Summary
Fixed the two HIGH and four MED findings from the `codex / gpt-6.1-sol` cross-model review of PR #201 in `core.hrms_skeleton`, each with regression tests; the component stays at `tested` with `reviewedBy: []` (Tier 3, awaiting Eldon's line-by-line review).

## Files touched
- `components/core/hrms_skeleton/service.py`: live context re-check on every operation and write (caller, session and store tenant, company); per-key lock around lookup and write, with one retry on a backend duplicate; applicant principal captured on filing and compared on decision; protected `Employee.user_id`; designated approver required for non-admin approvers.
- `components/core/hrms_skeleton/access.py`, `memory.py`, `frappe_backend.py`: `Store.key_lock` and `DuplicateKeyError`; in-memory lock; engine adapter lock (process lock plus database advisory lock, committed before release); `name` handled as a standard column.
- `components/core/hrms_skeleton/validation.py`: scale and canonical string read from the decimal's digits and exponent, no `normalize()`.
- `components/core/hrms_skeleton/specs.py`, `errors.py`, `strings.json`: `Employee` gains `gender` and `date_of_birth` (required); two new codes (`applicant_identity_unresolved`, `identity_binding_protected`) in Arabic and English; `applicant_user` refused from payloads.
- `components/core/hrms_skeleton/tests/`: new `test_service_hardening.py` (34 tests); `test_frappe_backend.py` now uses a fake that follows the pinned metadata rules; existing tests updated for the new mandatory Employee fields and the designated-approver rule. `manifest.json` lists the new test file.
- `components/core/hrms_skeleton/README.md`, `docs/open-questions.md` (Q-280 extended, no new Q number).

## Findings and regression tests
1. HIGH identity: `ApplicantIdentityTests`. 2. HIGH live context: `LiveContextTests`. 3. MED designated approver: `DesignatedApproverTests`. 4. MED atomic upsert: `AtomicUpsertTests` (barrier test) and `KeyLockTests`. 5. MED decimals: `ExactDecimalTests`. 6. MED metadata: `PinnedSchemaTests`.
Each guard was switched off in a scratch copy (no lock, `normalize()` back, no designated approver, cached caller) and the matching tests failed.

## Decisions
- No ADR. Existing changes of `Employee.user_id` are refused in `upsert`; no administrator operation to move a link exists yet (README, not-done list).
- An application cannot be filed for an employee with no linked account; this goes beyond the review and is easy to relax.
- The adapter commits inside `key_lock` before releasing the database lock so the next writer sees the record. UNVERIFIED on the bench (Q-280).
- Reused existing error codes for context drift (`session_invalid`, `tenant_mismatch`, `company_not_permitted`).
- Residual, documented: the approver named on an application is entered by the filer.

## Tokens or cost
Unknown.

## Next step
- Eldon: line-by-line Tier 3 review of PR #201; a different model re-checks these fixes.
- Partner: bench run to settle Q-280 to Q-282.
