# Session log: erp-013-review-fixes

Date: 2026-11-21
Author: partner
Tool and model: codex
Plan IDs: ERP-013

## Summary

Addressed PR #202's opening importer review findings and merged main's path-filtered CI.

## Files touched

- `.github/workflows/tests.yml` registers both ERP-013 files in the engine suite and routes Discovery prevalidation and connector changes to that suite.
- `docs/decisions/INDEX.md` retains both Proposed importer ADRs and every main row. `docs/open-questions.md` retains main's rows and the importer's Q-303, and adds Q-478.
- The importer, its README and the two ERP-013 test modules cover the changes below.

## Decisions

1. **Precision.** Debit, credit, AR/AP amounts and stock valuation rates exceeding the batch's currency precision return `IMP-PRECISION`. The tests cover every money field, trailing zeroes, an accepted `100.00` at precision 2 and a stored `100.005` at precision 3. The stock comparison still applies the documented rounding rule to the derived quantity-times-rate value.
2. **Audit.** Failure records append with the authenticated user ID. The offline reference store has no retention cap. Its migration retains existing rows and uses null for uncaptured historical user IDs. ERP-026 and SEC-008 track production audit durability and integrity.
3. **Negatives.** Negative inputs still fail closed. Q-478 asks the founders how to import credit-balance AR, debit-balance AP, negative stock and customer advances.
4. **Duplicates.** Repeated opening detail keys now return `IMP-DUPLICATE` before reconciliation, with coverage for accounts, customers, suppliers and item/warehouse pairs.
5. **Capabilities.** The default session has no capability. The SQLite roles map only with `CHANGE_ENGINE_ENV=dev` or `test`, tested with both role names under explicit production and unset configuration.
6. **Discovery contract.** A test pins the public `services.discovery.prevalidate` import, the call, its v1 report fields and its error type. All existing importer references already pointed to Q-303 for live posting and role mapping. Q-290 remains OPR-009, and ADR-0039 applicability remains UNVERIFIED.

## Verification

- Before the fixes, the focused run reported 18 failures and 2 passes. The Discovery interface and default-session tests passed against existing behavior.
- After the fixes, both ERP-013 suites passed all 120 tests.
- The script suite passed 22 tests and 29 subtests. Docs, repository hygiene, secret scan, plan independence and partner lane checks passed.
- Workflow YAML parsed. The filter selected both ERP-013 test paths and the Discovery dependencies, and refused an unmapped test. Diff checks found no conflict markers.

## Next step

Record Tier 3 founder review for ERP-013. Q-303 tracks production posting and role mapping. Q-478 requires a founder decision on negative balances.
