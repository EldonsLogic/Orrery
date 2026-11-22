# Session log: gov-065-tool-api-role-store

Date: 2026-11-22
Author: eldon
Tool and model: claude-code (Claude Opus 5.5, subagent)
Plan IDs: GOV-065

## Summary
Wrote ADR-0062 (Proposed) and changed Tool API section 4 step 2 to load the caller's roles from the regional role-assignment store (ADR-0060), fail closed on any lookup failure or empty set, as a patch bump 0.3.1 to 0.3.2.

## Files touched
- docs/decisions/ADR-0062-tool-api-roles-from-assignment-store.md: new ADR (number 0062; 0061 left for SEC-024).
- docs/decisions/INDEX.md: row for ADR-0062.
- contracts/tool-api.md: Version 0.3.2; section 4 step 2 wording and deny cases.
- contracts/README.md: Tool API version in the table (was stale at 0.3.0) now 0.3.2.
- docs/security/threat-model-contracts.md: trust-table row now names the regional store.
- docs/PLAN.md: GOV-065 done.

## Decisions
- [ADR-0062](../decisions/ADR-0062-tool-api-roles-from-assignment-store.md) (Proposed): patch bump, no wire change; outage error code left to the gateway ADR.

## Tokens or cost
Unknown.

## Next step
Cross-model security review and partner review of ADR-0062 (Tier 3); SEC-024 store design ADR. No code reads roles from the store until both are Accepted (ADR-0060 item 15).
- GOV-065 stays `doing` until ADR-0062 passes its security review and is Accepted.
