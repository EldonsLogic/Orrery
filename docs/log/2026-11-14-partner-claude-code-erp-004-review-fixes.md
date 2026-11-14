# Session log: erp-004-review-fixes

Date: 2026-11-14
Author: partner
Tool and model: claude-code (Claude Opus 5.5)
Plan IDs: ERP-004, ERP-024

## Summary
Applied Eldon's review of PR #50. ERP-004 is back to `doing`, Q-25 now has the engine's own MariaDB support range, and the MariaDB move is a new plan row (ERP-024).

## Files touched
- `docs/PLAN.md`:
  - ERP-004 goes from `done` back to `doing`. The policy is a draft, and Q-6, Q-15 and Q-25 to Q-27 are open.
  - New row ERP-024 (G1, partner): move the bench database off MariaDB 10.6.
- `docs/architecture/engine-version-policy.md` section 3, what the pinned engine supports:
  - Read from the bench's source, `frappe/database/mariadb/setup_db.py` lines 102 to 109. It warns below 10.6 ("not supported") and from 10.9 up ("not yet tested").
  - Every maintained MariaDB branch is therefore untested by the engine.
- `docs/architecture/engine-version-policy.md` section 3, end-of-life dates:
  - Third-party trackers give 10.11 2028-02-16, 11.8 2028-06-04 and 11.4 2029-05-29. All are UNVERIFIED, with URLs and access dates.
- `docs/architecture/engine-version-policy.md` section 6: "current breach of rule" becomes a finding.
  - The exposure rules are only PROPOSED (Q-27).
  - It is not urgent for a synthetic-data dev bench.
- `docs/open-questions.md`, Q-25: now names 11.4 as an option, adds the untested-range fact and links ERP-024.
- Merged `erp-005-core-module-scope` into this branch (no rebase, no force-push).
  - Resolved conflicts in `docs/PLAN.md`: both rows are now `doing`.
  - Regenerated `docs/STATUS.md`.

## Correction to the earlier log
`2026-11-14-partner-antigravity-erp-004-version-policy.md` reports that `check_docs` exited 1. The cause was a stale `docs/STATUS.md`, regenerated before the PR was opened. The PR body's "0 errors" is the result after regeneration.

## Decisions
- None. Q-25 stays with the founders.
- My recommendation is still a maintained LTS. It now rests on a bench test (ERP-024), not on the end-of-life dates alone.

## Tokens or cost
Unknown.

## Next step
Eldon re-reviews #50. ERP-024 waits for the Q-25 answer.
