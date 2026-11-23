# Session log: opr-013-review-round-2

Date: 2026-11-23
Author: eldon
Tool and model: claude-code / opus-5.5
Plan IDs: OPR-013

## Summary
Fixed the Fable re-review of PR #286 at 1c90b38 (R1 to R10). Tests first: the new tests were added and run red (16 failing) before the code changes, then green. OPR-013 stays `doing`.

## Files touched
- services/operate/runtime/schedule.py:
  - R1: the run deadline counts from the claim (clock read at claim time).
  - R2: only self-caused failures (`run_failed`, `tool_not_allowed`, `draft_only`) count toward suspension; new `resume` keeps the ledger, resets the count and is audited.
  - R3: one spend ledger per tenant and owner, with the owner's open holds counted.
  - R4: the agent gets plain functions holding only an opaque token; drafts rebuilt with `tainted: true` when recorded.
  - R5: window at least one day, so the maximum rate is USD 50 per owner per day.
  - R6: a long forward gap is a fresh start (ledger shifted); three consistent backward readings rebase.
  - R7: camelCase split; tokens generalledger, zakat, gosi, withholding, bank.
- services/operate/tests/runtime/test_schedule.py: 63 tests (two-tenant deadline, platform failures not counted, resume, recreate, context closures, draft rebuild, concurrent owner holds, gap and rebase, `MAX_CAP` and `MIN_PERIOD_S` pinned).
- docs/decisions/ADR-0064-scheduled-agent-authority-and-budgets.md (Proposed, this PR): items 2 to 8 match the code; R9 behaviour stated (fail, fail, pass is never suspended); two alternatives added.

## Decisions
- ADR-0064 refined in this PR (still Proposed, not accepted): owner-level ledger and window, self-caused failure count, owner resume, clock gap and rebase rules.

## Tests
- `python3 -m pytest services/operate/tests -q`: 688 passed, 1 skipped.
- Mutation run on `schedule.py`: 32 of 32 killed, including the seven Fable survivors (end-of-run re-check, tenant event filter, per-owner limit tenant scope, failure-count reset, role store list, missing kind or class, `MAX_CAP`).

## Tokens or cost
Unknown.

## Next step
- Fable re-check of #286, then the partner's Tier 3 review.
- Still UNVERIFIED: the real gateway's cost feed (Q-599), that `Principal` is built from the verified session, and that the tenant layer carries a real cap.
