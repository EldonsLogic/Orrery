# Session log: erp-005-review-fixes

Date: 2026-11-14
Author: partner
Tool and model: claude-code (Claude Opus 5.5)
Plan IDs: ERP-005

## Summary
Applied Eldon's review of PR #49. The ERP-005 row is back to `doing`, the spec now says Desk hiding is not enforcement, and the Q-22 question now covers negative amounts.

## Files touched
- `docs/PLAN.md`: ERP-005 goes from `done` back to `doing`.
  - The spec is a draft, most choices are PROPOSED, and Q-21 to Q-24 are open.
  - The row closes when Q-21 and Q-22 are answered, or when both founders accept the scope with them still open.
- `docs/specs/core-module-scope-trading.md`, section 5.1: says that Module Profile, Workspace `is_hidden` and Domain Settings change only Desk. Tenants never use Desk (ADR-0016).
  - Enforcement rests on role permissions (ERP-008) and the gateway or tool allow-list (PLT-024).
  - `Employee` sits in `Setup`, which cannot be blocked, so a Module Profile cannot hide it.
- `docs/specs/core-module-scope-trading.md`, other changes:
  - `Repost Item Valuation` and `Stock Reposting Settings` were listed as both "in scope" and "hidden from tenant roles". They now have one new status, `system-only`, defined in the status legend.
- `docs/open-questions.md`, Q-22: whatever rounding rule is chosen must state how negative amounts round, because credit notes and returns are negative.
  - "Commercial Rounding" is understood to round half away from zero, which equals `half_up` only for positive amounts.
  - This is UNVERIFIED, from memory.
- Merged `erp-001-dev-bench` into this branch to pick up the newer bench commits. It was a merge, not a rebase, so no force-push was needed.

## Decisions
- None.
- Q-21 (valuation) and Q-22 (rounding) touch Eldon's golden path and mapping fixture, so Eldon answers them.

## Tokens or cost
Unknown.

## Next step
Eldon re-reviews #49. ERP-005 closes once Q-21 and Q-22 are answered.
