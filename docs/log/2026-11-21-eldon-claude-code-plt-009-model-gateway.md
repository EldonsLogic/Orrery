# Session log: plt-009-model-gateway

Date: 2026-11-21
Author: eldon
Tool and model: claude-code / opus-5.5 (subagent)
Plan IDs: PLT-009

## Summary
Design for the AI model gateway (docs/architecture/model-gateway.md) and ADR-0053 (Proposed): tier and purpose routing with eval-admitted model tables per market, fallback only on transport failure and only to the same or stronger tier in region, nested budgets with a reservation that also caps provider output, fail closed when meter, secrets, kill flag or region policy is unavailable, platform-then-tenant prompt blocks with no cross-tenant cache, content-free traces, tests MG-001 to MG-017.

## Files touched
- docs/architecture/model-gateway.md: new design
- docs/decisions/ADR-0053-model-gateway.md: new, Proposed
- docs/decisions/INDEX.md: ADR-0053 row
- docs/open-questions.md: Q-543 (lane home, extends Q-127)
- docs/PLAN.md: PLT-009 set doing (build waits on Q-543)

## Decisions
- ADR-0053 Proposed. The only sensible home is services/gateway/ (partner lane): building waits on the founders' lane decision, Q-543 option (a) recommended.

## Tokens or cost
About 120k tokens (subagent).

## Next step
Founders decide Q-543/Q-127. Legal readings for KSA, UAE, Egypt and Qatar data transfer are UNVERIFIED (LEG-012 counsel); Egypt defaults to no personal data leaving the country until a PDPC licence exists. Provider in-region inference, retention and caching prices UNVERIFIED.
