# Session log: opr-013-scheduled-agents

Date: 2026-11-23
Author: eldon
Tool and model: claude-code / opus-5.5
Plan IDs: OPR-013

## Summary
First slice of OPR-013 (G3 row, started early under GATES.md; nothing counts as passed): a deterministic, port-based scheduler for agents with owner authority, draft-only runs, a per-run and per-period budget through the PLT-026 model-call port, fail-closed runs and an audit trail. No live scheduler, store or host wiring. Stacked on PR #244 (PLT-026); built alongside SEC-009 (#270) because that PR is not under this branch.

## Files touched
- services/operate/runtime/schedule.py: `Scheduler`, `Schedule`, `Principal`, `RunContext`, `RunRecord`, closed refusal `CODES`.
- services/operate/tests/runtime/test_schedule.py: 11 tests (fake clock, `FakeModelCallPort`): budget exhaustion and period reset, reservation failing at the port (meter down, run cap too small), tenant and owner mismatch (create, update, port bound to another tenant), role escalation and draft-only tools, owner losing the role, overlapping runs, clock edges (before start, exact boundary, same slot, missed slots, backwards, NaN, inf, None, bool), agent error and audit failure, schedule-change log.
- docs/decisions/ADR-0064-scheduled-agent-authority-and-budgets.md, docs/decisions/INDEX.md: Proposed ADR (agent authority, RULES 42).
- docs/open-questions.md: Q-597 (schedule audit types not in Contract 4), Q-598 (pause vs resume on exhaustion, R2 proposals).
- docs/PLAN.md: OPR-013 doing (more slices follow).

## Decisions
- [ADR-0064](../decisions/ADR-0064-scheduled-agent-authority-and-budgets.md) (Proposed, Tier 3). ADR number checked against open PRs and all branches (0061 to 0063 taken).

## Tests
`python3 -m pytest services/operate/tests -q`: 636 passed, 1 skipped (pytest 9.2.0).

## Tokens or cost
Unknown.

## Next step
- Partner line-by-line review and a different-model security review of ADR-0064 and `schedule.py`.
- OPR-013 next slices: durable schedule store, host tick and real gateway port, kill switch and ALP-025 trigger drop, Q-597 and Q-598 decisions.
- UNVERIFIED: the settle step reads the fake port's `events`; the real gateway port must expose committed cost per run the same way.

## Review fixes (Fable security review of PR #286 at cf31419)
#244 merged; `origin/main` merged in (conflicts in INDEX.md and open-questions.md resolved by keeping both sides). All twelve findings fixed in `schedule.py`, with tests in `test_schedule.py` (now 41 tests):
- F1: per-event costs only `int` 0..cap, otherwise the run settles at the full hold; a settle never lowers the total.
- F2: private `_Meter` wrapper forces taint and meters the run; `RunContext` exposes only `caller`, `complete`, `draft` (slots); drafts re-checked at the end, args deep-copied, drafts and `RunRecord` marked tainted.
- F3: clock check, schedule re-read, active and slot claim atomic under the lock; write-backs read the current schedule; two-thread test.
- F4: port must carry a `tenant` layer; spend kept in a ledger over a trailing window of the longest `period_s` ever set; at most 10 active schedules per owner; `MAX_CAP` USD 50 (defaults in ADR-0064 item 6, UNVERIFIED for pricing).
- F5: transition tools, `transitions[]`, `export`, missing kind or class on non-read tools and rigid-zone name tokens refused; reads are `get`/`list` with `kind: read`.
- F6: events filtered by type, tenant and run id, only new ones per call; Q-599 (partner) for a contract method.
- F7: suspension audited first and still applied if the audit fails; per-schedule isolation in `tick`; `roles_unavailable` recorded; `BaseException` settles spend and hard stops re-raise; unaudited failure reported as `audit_unavailable`; refused changes, overlap and clock faults audited; owner, on-behalf-of, time and slot in records.
- F8: forward step bounded (31 days) and an epoch ceiling; rejected readings not stored.
- F9 to F12: 600 s wall-clock limit (`run_timeout`); three consecutive failures suspend (`repeated_failures`; notification not built, in ADR); principal required for `period_spent`/`period_held`; `Principal.role_ids` must be a tuple; the six surviving mutations plus 12 more were re-run and all are killed.
- Q-597 and Q-598: Fable's opinions recorded as suggestions; still open for Eldon.
- Test-first note: tests were written with the fixes in one pass; each was then confirmed to fail with its fix reverted (mutation run, 18 of 18 killed).

Tests: `python3 -m pytest services/operate/tests -q`: 666 passed, 1 skipped.
