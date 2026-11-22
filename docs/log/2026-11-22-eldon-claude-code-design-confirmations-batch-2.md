# Session log: design-confirmations-batch-2

Date: 2026-11-22
Author: eldon
Tool and model: claude-code / Opus
Plan IDs: GOV-060

## Summary
Checked 21 candidate "confirm or decide" open questions against the code end to end and recorded the ones the code answers in ADR-0058: 2 resolved, 5 decided and kept open until their plan row lands, 14 left open.

## Files touched
- docs/decisions/ADR-0058-design-confirmations-batch-2.md: new ADR (Proposed), decisions with file:line evidence and the rows left open with reasons.
- docs/decisions/INDEX.md: ADR-0058 added.
- docs/open-questions.md: Q-109, Q-112 marked RESOLVED; Q-61, Q-76, Q-90, Q-119, Q-139 prefixed DECIDED, pending their row, and kept open.
- docs/PLAN.md: GOV-060 (doing); follow-ups BPL-039 (incremental compile with inverse, Q-61, Q-76) and SEC-023 (contact-detail changes in the action policy table R4 row, Q-139), both todo, eldon.

## Decisions
- [ADR-0058](../decisions/ADR-0058-design-confirmations-batch-2.md). Resolved: Q-109 (keep CON-010 plus class name, no connector code passed through), Q-112 (keep ODO-). Decided, pending: Q-61 and Q-76 (BPL-039), Q-90 (INF-014, existing partner row, no new obligation), Q-119 (BRD-011, self-hosting already in ADR-0022), Q-139 (SEC-023).
- Dropped (left open): Q-53 and Q-77 (canonical adapter id obliges the partner's real adapter), Q-87 (approval authority; proposed reset conflicts with the framework protecting buildState), Q-91 and Q-97 (security), Q-98 and Q-120 (thin), Q-116 (founder confirmation), Q-133 (contract catalog change and Arabic review), Q-146 (premise weaker than stated: the picker emits Gregorian ISO; dependency choice open), Q-147 and Q-148 (identity security), Q-179 (gateway, partner), Q-264 (multi-part, placeholders, OPR-020).

## Tokens or cost
Unknown.

## Next step
Partner review of ADR-0058 (GOV-060). Then BPL-039 and SEC-023 when picked.
