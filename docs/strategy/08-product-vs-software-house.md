# 08 - Product, not software house: plan and metrics

Date: 2026-11-04. We build the first clients ourselves. This plan makes that safe by tying every build to platform improvement and measuring it.

## Rules (put in AGENTS.md once Phase 2 is approved)
1. **No client-specific code, ever.** A need that no component covers becomes a candidate component: built once, reviewed, tested, added to the library, available to all tenants. If it cannot be generalised, we decline or price it as an explicit exception.
2. **Every build produces three deliverables:** the client's live system; new or improved library components; new eval cases and migration mappings.
3. **Exceptions register.** Any manual step (human edited a Blueprint, hand-fixed a mapping) is logged with a reason. The register is the backlog for automation.
4. **Contract terms:** fixed-price setup (so labour overruns hurt us and force automation), anonymised-blueprint reuse clause, no free pilots (`05`, `07`).
5. **Gate the roadmap by metrics.** If autonomy stalls for two consecutive clients, stop selling and fix the platform.

## Metrics (reported monthly in `docs/HANDOFF.md` or a metrics file)
| Metric | Definition | Client 1 | Client 5 | Client 10 | Client 20 |
|---|---|---|---|---|---|
| **Platform Autonomy Rate** | Share of Blueprint elements (entities, fields, workflows, roles, reports, print formats, integrations) produced by compiler from library without human edits | 30% | 60% | 75% | 85% |
| Human hours per go-live | Founders + contractors, all-in | 200 | 120 | 60 | 30 |
| Time to go-live | Contract to production | 8 wks | 5 | 3 | 2 |
| Component reuse ratio | % of components used by 2+ tenants | n/a | 40% | 60% | 75% |
| New components per build | Count added to library | many | 5-8 | 2-4 | 0-2 |
| Client-specific code lines | Lines outside library | 0 | 0 | 0 | 0 |
| Arabic eval pass rate | Release gate | 85% | 90% | 93% | 95% |
| Services share of revenue | Setup + custom / total | ~70% | ~50% | <35% | <25% |
| Setup gross margin | (setup - human cost) / setup | 20-30% | 55% | 75% | 90% |
These targets are my hypotheses, not benchmarks; set them with the founders and revise after client 1.

## What investors will read from this
A rising autonomy rate with falling human hours is the proof of software margins and of a compounding library. A flat line means a services company. We should show the chart from the first pilot.

## Pilots as flywheel inputs
- **Pilot A (greenfield):** produces the interview playbook, the first vertical Blueprint template, and the baseline human-hours number.
- **Pilot B (Odoo migration):** produces the Odoo extractor, the field-mapping library and the "why they leave" case. Keep it generic until specifics are cleared (founder instruction 2026-11-04).
- Detailed discovery plans come in Phase 3.

## Staffing guardrail
Founders do the first builds; the second build must reuse at least 30% of the first. Do not hire implementers before the autonomy rate passes ~60%; hire platform/eval engineers first. A rising implementer headcount is the leading indicator of the software-house trap.
