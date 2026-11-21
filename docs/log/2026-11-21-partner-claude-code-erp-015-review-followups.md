# Session log: erp-015-review-followups

Date: 2026-11-21
Author: partner
Tool and model: claude-code (Claude Opus 5.5, coordinator)
Plan IDs: ERP-015,ERP-031

## Summary
Records the four non-blocking Lows from Eldon's approving review of PR #229 (ERP-015, merged as f7f6998) in the plan and open questions; no code changes.

## Files touched
- `docs/open-questions.md`:
  - **Q-514:** adds the follow-up (L1). An accountant confirms rule (a), and an ADR beside ADR-0033 records it, before stock goes live.
  - **Q-555:** notes it blocks stock go-live, not ERP-015 (L4).
  - **Q-557 (new):** 3-decimal quantity input vs 2-decimal ledger storage, and the untested partial issue (L2). Q-556 is skipped because the open ERP-013 follow-up PR claims it.
- `docs/PLAN.md`: ERP-031 row text adds a live back-dated issue and transfer, and fails when a repost reports `Skipped` (L3).

## Decisions
- None. The founder approved handling these Lows in a follow-up (2026-11-21).

## Corrections to earlier logs
- `2026-11-21-partner-claude-code-plan-status-partner-rows.md` (PR #243), CE-SEC-005 row: `real-bench-tests` was not green on every main-based PR run on 2026-11-21. Run 44893242651 on `erp-020-engine-headless` failed before that PR's token fix. The latest runs execute 16 live tests, not 15.
- Same log, ERP-027 row: Eldon's `52c348b` comment said a Tier 3 line-by-line review was still needed; no separate Tier 3 approval is recorded, and he merged #125 himself after CI passed.

## Tokens or cost
Unknown.

## Next step
- **ERP-031:** wire the live valuation layers into real-bench CI.
- **Q-514 and Q-557:** need an accountant or founder answer before stock goes live.
