# Session log: erp-005-close-valuation-rounding

Date: 2026-11-14
Author: partner
Tool and model: claude-code (Claude Opus 5.5)
Plan IDs: ERP-005

## Summary
Recorded the founders' answers to Q-21, Q-22 and Q-28 in ADR-0033, confirmed the two engine settings on the bench, and closed ERP-005.

## Files touched
- `docs/decisions/ADR-0033-v1-valuation-rounding-and-arabic-review.md`: new, Accepted. Moving Average set explicitly, Commercial Rounding including negative amounts, and the Q-28 review rule, with bench evidence.
- `docs/decisions/INDEX.md`: ADR-0033 row.
- `docs/open-questions.md`: Q-21 and Q-22 struck as resolved by ADR-0033. Q-25 carries the founder answer and stays open until ERP-024. Q-28 is not on main yet; PR #51 records its answer.
- `docs/specs/core-module-scope-trading.md`: section 5 and section 8 now show the decisions. Status changed from draft to accepted for G1; Q-23 and Q-24 stay open.
- `docs/PLAN.md`: ERP-005 set to `done`. Eldon's condition on #49 was that Q-21 and Q-22 are answered, and they now are.

## Evidence (bench, synthetic data only)
- Created a throwaway site `gpcheck.localhost` on the running pinned bench, ran the setup wizard with a synthetic SAR company, ran the checks, then dropped the site with no backup. The main synthetic site was not touched.
- Results are in ADR-0033:
  - Moving Average: 115, then 5 out at 115 (-575), then 126.25.
  - Commercial Rounding is symmetric: -2.5 → -3, -0.125 → -0.13, -0.105 → -0.11.
  - The invoice's tax of 0.11 is mirrored by the credit note's -0.11.
  - The legacy default rounds negative halves towards zero, so it is not symmetric.
- The check script was a session helper and is not committed.

## Decisions
- ADR-0033 records the founders' decisions. This session decided nothing new.

## Tokens or cost
Unknown.

## Next step
Eldon reviews this PR. ERP-003 (provisioning) and ERP-021 must set and verify both settings. ERP-024 tests a MariaDB LTS for Q-25.
