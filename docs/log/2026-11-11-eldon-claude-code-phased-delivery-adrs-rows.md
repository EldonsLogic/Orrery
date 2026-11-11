# Session log: phased-delivery-adrs-rows

Date: 2026-11-11
Author: eldon
Tool and model: claude-code / sonnet-5.5
Plan IDs: GOV-036,BPL-028,BPL-029,ERP-021,QA-018,SEC-019,CMP-032

## Summary
Wrote the phased delivery document with lanes and the phase to gate map, four proposed ADRs, 19 new plan rows and the phase exit plan rows, for the partner to review.

## Files touched
- docs/architecture/phased-delivery-and-lanes.md: phases 0, 1A, 1B, 2, 3, 4, market-pack track, phase to gate map, lane split by phase, open decisions
- docs/decisions/ADR-0026 to ADR-0029 and INDEX.md: Proposed; phased delivery, human floor and agent authority, recoverable change apply, engine disclosure and SaaS-first
- docs/PLAN.md: rows GOV-036 to GOV-039, BPL-028 to BPL-030, ERP-021 to ERP-023, QA-018 to QA-020, SEC-019, SEC-020, LEG-019, CMP-032, OPR-016
- docs/specs/phase-exit-criteria.json: plan rows per phase
- docs/ONBOARDING.md: pointer to the proposed phased delivery
- docs/specs/golden-path-trading-sale.md: draft golden path (BPL-028 now doing); no accountant needed before Phase 2, other founder checks independently

## Decisions
- ADR-0026, ADR-0027, ADR-0028, ADR-0029 (all Proposed, approval pending). Founder decision 2026-11-11: Qatar first pilot market, the other markets follow right away in the build as a parallel track. Partner positions from his written responses are reflected, not yet agreed in writing.

## Tokens or cost
Not measured.

## Next step
Partner reviews this PR and the stacked foundation PR. Then GOV-037 (edit GATES.md after both approve), BPL-028 golden path with an accountant, ERP-021 bench proofs (partner). Security items the partner reported go through SECURITY.md, not this log. Independent Opus review found issues (lane placement, misquoted gate text, public-repo exposure, SaaS wording); fixed before push. Contracts BPL-025 and BPL-026 need the ADR-0028 wording.
