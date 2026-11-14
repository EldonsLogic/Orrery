# ADR-0026: Phased delivery, phase exits and the market-pack track

Status: Proposed
Owner: eldon
Approved by: pending (partner review of the pull request)

## Context
The founders and an independent review agreed that the product should be proven in steps, not built as described in one go. The partner's responses asked for a smaller first proof, real-engine integration, pilot safeguards and a gate map. The repository has gates G0 to G5 ([../GATES.md](../GATES.md)) and ADR-0024 (four phase-1 markets, no fixed launch order). The first leads are in Qatar. The full plan is in [../architecture/phased-delivery-and-lanes.md](../architecture/phased-delivery-and-lanes.md).

## Decision
- Delivery runs in phases 0 (engine proof), 1A (manual golden system), 1B (builder reproduction), 2 (pilot), 3 (repeatability), 4 (scale). Each closes only after a recorded exit run (RULES 48).
- Qatar is the intended first pilot market (the first leads are there). Per ADR-0024 it is confirmed only by readiness: verified Qatar research (CMP-030), a built Qatar pack (CMP-031), the lead, an accountant and the hosting and data-transfer position, all before real data. Until then Qatar-first is a hypothesis. This is consistent with ADR-0024 and needs no superseding ADR. The UAE, Saudi Arabia and Egypt packs follow right away in the build as a managed parallel track in readiness order. Each active pack has a named owner, a capacity limit and a country release checklist; none blocks the Qatar pilot; none receives real customer data before its own review.
- Library-first: customers may add fields of permitted types to library record types; new record types are authored by our team as components; no customer scripts. Ordinary master data (for example a new warehouse) is not a schema change.
- Pilot safeguards are two checkpoints: before receiving real data, and before live posting.
- At most one draft-only agent in the pilot, chosen with the lead; the core must work with agents off.
- Hours, percentages and unaided-share figures from the review are hypotheses, not release gates.
- Proposed gate wording changes (made by GOV-037 after both founders approve): G1's Saudi sandbox criterion becomes a Saudi release criterion and first-pilot compliance depends on the chosen market; G1's "applies, diffs and rolls back" follows ADR-0028 (recoverable, not universal rollback); the one-month simulation in G2 is optional; G3's UAE and payroll line is per market; the Arabic invoice print format for the golden path is split from the ZATCA Phase 1 dependency (ERP-007 depends on CMP-003 today) so a Saudi item does not block the Qatar pilot.

## Alternatives rejected
- A fixed market order for all phases: contradicts ADR-0024 and ties the pilot to other packs.
- One build wave for all four markets: Egypt and Qatar rules are unresearched; packs are built as research is verified.
- Self-serve first: no evidence yet that buyers want it; assisted setup measures the real effort.

## Consequences
- New plan rows (GOV-036 to GOV-039, BPL-028 to BPL-030, ERP-021 to ERP-023, PLT-025, QA-018 to QA-020, SEC-019, SEC-020, LEG-019, CMP-032, OPR-016) and a phase exit criteria file.
- GATES.md stays unchanged until GOV-037; until then the phase-to-gate map is guidance.
- Capacity for parallel market packs must be agreed by both founders (GOV-039).

## Supersedes
None. Clarifies ADR-0024 and refines how GATES.md is applied.
