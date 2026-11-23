# Session log: gov-059-open-questions-triage

Date: 2026-11-21
Author: eldon
Tool and model: claude-code (Opus 5.5 orchestrating; five Sonnet 5.5 read-only triage agents)
Plan IDs: GOV-059

## Summary
Triaged all 378 rows of docs/open-questions.md and closed 18 that merged ADRs, contracts or code answer, each with its evidence. The remaining open rows split into 110 founder decisions and 232 technical items. Most of the technical items were classified from their row text, not checked one by one against code.

## Results
- Already closed: 16. Closed now: 18. Q-19, Q-103, Q-106, Q-114, Q-152, Q-153, Q-154, Q-250 and Q-282 are RESOLVED with evidence. Q-32 to Q-40 are SUPERSEDED by Q-45 to Q-49 (contracts/engine-adapter.md 0.1.2).
- Kept open on purpose:
  - Q-147: it asks for a confirmation, and ADR-0047 is still Proposed.
  - Q-28: partner-owned; ADR-0033 section 3 appears to answer it, so the partner should close it.
- Founder decisions still open: 110. 2 are needed by G0 (Q-3, Q-7) and 29 by G1 (listed in the PR). The rest are G2 or later.
- Technical items still open: 232. The triage was shallow, so a deeper pass against code and merged PRs may close more.

## Files touched
- docs/open-questions.md: 18 rows marked RESOLVED or SUPERSEDED; the original question is kept after "Was:".
- docs/PLAN.md: row GOV-059.

## Decisions
- None. No founder decision was taken; questions were closed only where an artefact on main answers them.

## Tokens or cost
About 445k subagent tokens for the triage.

## Next step
- Founders: answer the G0 and G1 decisions (Q-3, Q-7, then the G1 list).
- Partner: close Q-28 and check the partner-owned items.
- Optional: a deeper per-row pass over the 232 technical items.
