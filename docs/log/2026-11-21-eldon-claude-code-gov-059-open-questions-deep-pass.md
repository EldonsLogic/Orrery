# Session log: gov-059-open-questions-deep-pass

Date: 2026-11-21
Author: eldon
Tool and model: claude-code (Opus 5.5 orchestrating; five Sonnet 5.5 read-only agents)
Plan IDs: GOV-059

## Summary
A second, deeper pass over the 232 technical open questions. Each row was checked against commits, merged PRs, code and contract lines, and plan row status. The pass closed 3 rows and narrowed 16. The other 206 have a named blocker, and 6 turned out to need a founder decision.

## Results
- **Closed:**
  - Q-12: hijridate, plus announced-date and audited override layers.
  - Q-274: sealed sign-off ledger, PR #223.
  - Q-351: zero-regression agent-behaviour gate, PR #218.
- **Narrowed:** Q-6, Q-16, Q-90, Q-122, Q-126, Q-135, Q-163, Q-177, Q-181, Q-182, Q-203, Q-223, Q-225, Q-258, Q-265 and Q-381 each gain an "Update 2026-11-21" sentence saying what is answered and what remains. Q-254 (a security row) was left unchanged.
- **Founder decisions found:** Q-94, Q-130, Q-143, Q-178, Q-226 and Q-240.
- **Common blockers for the rest:** PLT-009 (model gateway), PLT-024, OPR-004 (tool API), OPR-020, ERP-013 and ERP-009 bench runs, staging (INF-003), and contract changes not yet made (events.md, tool-api error catalog).
- **About 28 rows ask an agent to "confirm" a compiler or design choice** that no ADR records (Q-50 to Q-85 range). One ADR could settle them.

## Files touched
- docs/open-questions.md: 3 closed and 16 narrowed.

## Decisions
- None.

## Tokens or cost
About 490k subagent tokens.

## Next step
- Optional: one ADR deciding the "confirm" design questions in Q-50 to Q-85.
- Founders: the six decisions listed above.
