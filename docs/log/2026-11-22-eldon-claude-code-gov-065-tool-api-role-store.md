# Session log: gov-065-tool-api-role-store

Date: 2026-11-22
Author: eldon
Tool and model: claude-code (Claude Opus 5.5, subagent)
Plan IDs: GOV-065

## Summary
Wrote ADR-0062 and changed Tool API section 4 step 2 to load a member caller's roles from the regional assignment store (ADR-0060), fail closed on any lookup failure or empty set, as a patch bump 0.3.1 to 0.3.2. Fable 5.2's security review (PR #276) was ACCEPT WITH CONDITIONS; C1 (re-read on approved execution, lagging replica counts as a cache, no fallback switch) and Lows L1-L5 are applied, and ADR-0062 is Accepted on Eldon's decision with the partner's review as the second founder's record.

## Files touched
- docs/decisions/ADR-0062-tool-api-roles-from-assignment-store.md: new ADR (number 0062; 0061 left for SEC-024).
- docs/decisions/INDEX.md: row for ADR-0062.
- contracts/tool-api.md: Version 0.3.2; section 4 step 2 wording and deny cases.
- contracts/README.md: Tool API version in the table (was stale at 0.3.0) now 0.3.2.
- docs/security/threat-model-contracts.md: trust-table row now names the regional store.
- docs/PLAN.md: GOV-065 done after the review conditions were applied.
- docs/open-questions.md: Q-584 (error code for a role-store outage).

## Decisions
- [ADR-0062](../decisions/ADR-0062-tool-api-roles-from-assignment-store.md) (Accepted with review conditions): patch bump, no wire change; outage error code left to the gateway ADR (Q-584).

## Tokens or cost
Unknown.

## Next step
Partner review of PR #276; SEC-024 store design ADR; Q-584. No code reads roles from the store until the SEC-024 design ADR is Accepted (ADR-0060 item 15).
