# Session log: erp-013-server-precision

Date: 2026-11-21
Author: partner
Tool and model: codex / gpt-6.2-sol
Plan IDs: ERP-013

## Summary
Addressed the Tier 3 review blocker on PR #202 by deriving opening import precision from the batch currency on the server.

## Files touched
- `apps/engine/change_engine/change_engine/importer/validation.py` derives precision from a server-owned minor-unit table and refuses mismatched metadata.
- `apps/engine/change_engine/change_engine/importer/README.md` documents accepted metadata and both validation errors.
- `apps/engine/change_engine/change_engine/tests/test_erp_013_review_fixes.py` covers SAR overprecision and mismatched metadata across validate, preview and apply, plus exact storage of accepted amounts.
- `apps/engine/change_engine/change_engine/tests/test_erp_013_opening_importer.py` covers equivalent confirmation hashes for omitted and matching precision, currency binding and exact stock reconciliation at two decimal places.

## Decisions
- Omitted precision and an explicitly matching integer produce the same plan hash. Unknown currencies and mismatched precision return `IMP-SCHEMA`. Excess monetary decimal places return `IMP-PRECISION`.
- ISO 4217 minor units in the offline table are marked UNVERIFIED because the source was not re-fetched.

## Verification

- On the reviewed head, four tests exposed acceptance of mismatched precision and 136 passed. With the fix, all 140 ERP-013 tests passed. A synthetic check changed only the server-derived precision and confirmed that the plan hash changed.
- The script suite passed 22 tests and 29 subtests. Docs, repository hygiene, secret scan and plan independence passed.
- The direct lane check against `origin/main` flagged paths on newer main commits. The lane check passed against the merge base used by CI.

## Tokens or cost
Unknown.

## Next step
ERP-013 awaits Tier 3 re-review on PR #202.
