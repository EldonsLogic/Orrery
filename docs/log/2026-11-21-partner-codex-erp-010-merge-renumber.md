# Session log: erp-010-merge-renumber

Date: 2026-11-21
Author: partner
Tool and model: codex
Plan IDs: ERP-010

## Summary
Merged main into PR #201 and reassigned the ERP-010 questions to Q-475, Q-476 and Q-477 because main uses the original numbers for OPR-009.

## Files touched
- `.github/workflows/tests.yml` registers the HR skeleton tests in the path filter and runs them in the components suite.
- `docs/open-questions.md` adds the three renumbered ERP-010 rows after Q-474.
- The HR skeleton README, backend, specs and backend tests use the new question numbers.

## Decisions
- ERP-010's former Q-280, Q-281 and Q-282 map to Q-475, Q-476 and Q-477 respectively. Older session logs retain the original numbers.

## Next step
Continue Tier 3 review of PR #201.
