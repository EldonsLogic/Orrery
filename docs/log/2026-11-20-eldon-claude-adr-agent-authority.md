# Session log: adr-agent-authority

Date: 2026-11-20
Author: eldon
Tool and model: claude
Plan IDs: OPR-001

## Summary
Drafted ADR-0048 (Proposed): agent authority (propose vs act, allow-list, R1-R4, taint, caps, validator split, audit, kill switch, forbidden list). Closes the ADR owed by Q-258; docs only.

## Files touched
- docs/decisions/ADR-0048-agent-authority-propose-not-act.md: new, Proposed
- docs/decisions/INDEX.md: index row

## Decisions
- ADR-0048 (Proposed, Tier 3). Renumbered from 0047 because the MFA ADR (PR #206) took 0047.

## Tokens or cost
Unknown.

## Next step
Other founder's review plus different-model security review; then OPR-004/ERP-023 enforcement at the Tool API (OPR-001, OPR-017).
