# Session log: independent-lanes

Date: 2026-11-07
Author: eldon
Tool and model: claude-code
Plan IDs: GOV-032,BPL-025,BPL-026,BPL-027,SEC-018,CMP-030,GTM-019

## Summary
Founder asked that his and the partner's work be mutually exclusive in every phase. Assigned all 210 unowned plan rows by lane, found 11 cross-founder dependencies inside a gate and fixed each by moving a gate or splitting an interface row, added interface rows BPL-025 (engine adapter contract and fake), BPL-026 (compiled-artifact contract), BPL-027 (integration) and SEC-018, and added a plan independence check to the docs gate, CI, pre-push and finish gate (ADR-0025). Qatar rows CMP-030 and GTM-019 are owned by Eldon.

## Files touched
- docs/PLAN.md (owners, 11 gate moves, 5 dependency edits, 5 new rows), scripts/check_plan_independence.py (new) and check_docs.py hook, scripts/lanes.json (connectors/ and services/control-plane/ to Eldon, services/gateway/ to partner), docs/ONBOARDING.md, AGENTS.md, docs/decisions/ADR-0025 and INDEX.

## Decisions
- ADR-0025. Eldon holds about 178 open rows and the partner about 79 (G2: 92 versus 20); rebalance by changing Owner in a PR before G2 starts. Partner must read BPL-025 and BPL-026 contracts before building the adapter and apply.

## Tokens or cost
Unknown or approximate, if known.

## Next step
Eldon: BPL-025 and BPL-026 interface contracts (they unblock the partner's BPL-012 and BPL-007), then BRD-006, BRD-004. Partner: ERP-001, CE-SEC-003, then BPL-012 against BPL-025.
