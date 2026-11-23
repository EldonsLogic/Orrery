# Session log: opr-013-review-round-3

Date: 2026-11-23
Author: eldon
Tool and model: claude-code / opus-5.5
Plan IDs: OPR-013

## Summary
Fixed the third security check of PR #286 at 0f95aa4 (Sonnet standing in for Fable): N1 and L1 to L4. Merged `origin/main` first. Tests first: the new tests were run red (12 failing) before the code changes, then green. OPR-013 stays `doing`.

## Files touched
- services/operate/runtime/schedule.py:
  - N1: `_rebase` keeps ledger rows unchanged and only raises slot marks, so no slot replays and the cap binds.
  - L1: raw errors from the tool-definition store, the port factory and `port.complete` become `platform_unavailable`, which does not count toward suspension.
  - L2: `resume` refuses an active schedule (`already_active`).
  - L4: rigid-zone words matched as substrings of the flattened lowercased name, with `gl` and `vat` as whole tokens only.
- services/operate/tests/runtime/test_schedule.py: 77 tests (rebase back 2 days and forward 2.1 days with the cap binding and unique run ids, platform errors not counted, resume on an active schedule, 10 new blocked names, ordinary names still schedulable).
- docs/decisions/ADR-0064-scheduled-agent-authority-and-budgets.md (Proposed, this PR): items 2, 3, 4 and 7 updated; L3 documented, not engineered around.

## Decisions
- ADR-0064 refined in this PR (still Proposed). After a far-future clock reading the scheduler ticks again but stays fail closed: no slot replay, and spend recorded ahead of now keeps counting until an operator action in a later slice.

## Tests
- `python3 -m pytest services/operate/tests -q`: 702 passed, 1 skipped.
- Mutation run on `schedule.py`: 40 of 40 killed.

## Tokens or cost
Unknown.

## Next step
- Re-check of #286, then the partner's Tier 3 review.
- UNVERIFIED: the real gateway's cost feed (Q-599), that `Principal` is built from the verified session, that the tenant layer carries a real cap, and that the production clock is monotonic.
