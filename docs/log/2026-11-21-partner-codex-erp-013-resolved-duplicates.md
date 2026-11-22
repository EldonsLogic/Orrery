# Session log: erp-013-resolved-duplicates

Date: 2026-11-21
Author: partner
Tool and model: codex
Plan IDs: ERP-013

## Summary

Addressed PR #202 review comment 7060905749. Opening rows with the same resolved master key tuple now return `IMP-DUPLICATE` before reconciliation.

## Files touched

- `importer/validation.py` checks duplicates during master resolution for TrialBalance, AR, AP and Stock.
- `importer/README.md` documents the rule. `tests/test_erp_013_review_fixes.py` covers case, whitespace and aliases for AR and both Stock links, plus distinct stock pairs.

## Decisions

The importer uses the stable business key of each resolved record, including incoming masters. The resolver controls which spellings identify a record. Stock uniqueness uses both the item and the warehouse.

## Verification

- Before the fix, nine regressions failed and the distinct-pair control passed. Five duplicate cases were accepted and four returned `IMP-REPORT`.
- After the fix, all ten focused cases and all 130 ERP-013 tests passed. The script suite passed 22 tests and 29 subtests.
- Docs, repository hygiene and secret checks passed.

## Next step

ERP-013 awaits Tier 3 review. Q-303 tracks live posting and role mapping.
