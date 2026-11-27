# Session log: module-scope

Date: 2026-11-27
Author: eldon
Tool and model: claude-code / opus-5.5
Plan IDs: GOV-078

## Summary
Opened the phase-1 module scope PR: ADR-0076 (Proposed) adds ten modules as Blueprint components, contracts and ADRs only, with the partner's 2026-11-27 answers adopted as constraints; module map, PRD note and 24 plan rows. Nothing built, pinned or installed.

## Files touched
- docs/decisions/ADR-0076-phase-1-module-scope.md: new ADR (Proposed; Eldon approved, partner pending).
- docs/decisions/INDEX.md: ADR-0076 row.
- docs/product/module-map.md: ten modules moved into phase 1 with a status each (contracts now, build after GPL, deferred, rigid zone); not-doing list lifts manufacturing depth and e-commerce, keeps POS-first retail deferred and filing tax or zakat not-doing.
- docs/product/PRD.md: one-line pointer to ADR-0076 under the not-doing list.
- docs/PLAN.md: GOV-078 (doing) and follow-ups DSC-021 to DSC-024, BPL-052 to BPL-059, WEB-031 to WEB-035, ERP-042, ERP-043, CMP-048 to CMP-051.

## Id checks
- First pushed as ADR-0075 and BPL-051 to BPL-058; PR #391 (bpl-051-link-target-order) took ADR-0075 and BPL-051 meanwhile, so this PR moved to ADR-0076 and BPL-052 to BPL-059 (coordinator heads-up).
- ADR-0076 re-checked unused on main and every open PR branch (ADR-0074 on #388, ADR-0075 on #391).
- Plan ids checked against main and every open PR branch: highest GOV-077, BPL-051 (#391), CMP-047, DSC-020, ERP-041, WEB-030; the new ids follow those.

## Decisions
- [ADR-0076](../decisions/ADR-0076-phase-1-module-scope.md) (Proposed): phase-1 module scope. Partner approval pending on this PR.
- Partner rows for sayegh9 to accept: BPL-056 to BPL-059 (component builds, G2), ERP-042 and ERP-043 (blocked on ADR-0074), CMP-048, CMP-049, CMP-051 (blocked or held, rigid zone).

## Tokens or cost
Unknown.

## Next step
Partner reviews ADR-0076 and accepts the partner rows. Eldon's lane can start the G1 contract rows: DSC-021, DSC-022, BPL-052 to BPL-055, and CMP-050.
