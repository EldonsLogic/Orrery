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
