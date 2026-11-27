# Session log: module-scope

Date: 2026-11-27
Author: eldon
Tool and model: claude-code / opus-5.5
Plan IDs: GOV-078

## Summary
Opened the phase-1 module scope PR: ADR-0075 (Proposed) adds ten modules as Blueprint components, contracts and ADRs only, with the partner's 2026-11-27 answers adopted as constraints; module map, PRD note and 24 plan rows. Nothing built, pinned or installed.

## Files touched
- docs/decisions/ADR-0075-phase-1-module-scope.md: new ADR (Proposed; Eldon approved, partner pending).
- docs/decisions/INDEX.md: ADR-0075 row.
- docs/product/module-map.md: ten modules moved into phase 1 with a status each (contracts now, build after GPL, deferred, rigid zone); not-doing list lifts manufacturing depth and e-commerce, keeps POS-first retail deferred and filing tax or zakat not-doing.
- docs/product/PRD.md: one-line pointer to ADR-0075 under the not-doing list.
- docs/PLAN.md: GOV-078 (doing) and follow-ups DSC-021 to DSC-024, BPL-051 to BPL-058, WEB-031 to WEB-035, ERP-042, ERP-043, CMP-048 to CMP-051.

## Id checks
- ADR-0075 was unused on main and on all 26 open PR branches (highest elsewhere: ADR-0074 on #388).
- Plan ids checked against main and every open PR branch: highest GOV-077, BPL-050, CMP-047, DSC-020, ERP-041, WEB-030; the new ids follow those.

## Decisions
- [ADR-0075](../decisions/ADR-0075-phase-1-module-scope.md) (Proposed): phase-1 module scope. Partner approval pending on this PR.
- Partner rows for sayegh9 to accept: BPL-055 to BPL-058 (component builds, G2), ERP-042 and ERP-043 (blocked on ADR-0074), CMP-048, CMP-049, CMP-051 (blocked or held, rigid zone).

## Tokens or cost
Unknown.

## Next step
Partner reviews ADR-0075 and accepts the partner rows. Eldon's lane can start the G1 contract rows: DSC-021, DSC-022, BPL-051 to BPL-054, and CMP-050.
