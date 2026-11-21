# Session log: bpl-036-design-confirmations

Date: 2026-11-21
Author: eldon
Tool and model: claude-code
Plan IDs: BPL-036

## Summary
Decided 22 "confirm" rows from docs/open-questions.md (compiler, token resolver, Studio, migration) in one ADR, ADR-0057 (Proposed, partner review pending). No code changed.

## Files touched
- docs/decisions/ADR-0057-compiler-and-studio-design-confirmations.md: new ADR, decision table with file:line rationale.
- docs/decisions/INDEX.md: ADR-0057 row.
- docs/open-questions.md: 22 rows marked RESOLVED (ADR-0057).
- docs/PLAN.md: BPL-036 row (done).

## Decisions
- [ADR-0057](../decisions/ADR-0057-compiler-and-studio-design-confirmations.md).
- Keep: Q-50, Q-52, Q-54, Q-55, Q-56, Q-58, Q-60, Q-66, Q-67, Q-68, Q-69, Q-70, Q-71, Q-72, Q-73, Q-75, Q-78, Q-81, Q-82, Q-86.
- Change (not implemented): Q-51 (exempt settings.set from the (kind, pointer) rule in the artifact contract), Q-64 (validator rule 10 to use the resolver's derive).
- Excluded, left open:
  - Q-59: ledger or tax risk classification.
  - Q-74: tenant slug source is a tenancy question.
  - Q-79: auto-granted approvals touch approval authority (ADR-0048, ADR-0049).
  - Q-80: ZATCA QR inputs are e-invoicing.
  - Q-83, Q-84, Q-85: injection suite is security; Q-84 depends on PLT-009, Q-85 on a real adapter.
  - Q-88: unsure; the Blueprint schema file is 0.4.0 while meta.schemaVersion and the migrator are 0.1.0, so the row's premise fails on main (tied to Q-89).
  - Q-93: confusable handling is untrusted-content defence (security).

## Tokens or cost
Unknown.

## Next step
Partner review of ADR-0057. Follow-up work without plan rows: a contract patch (compiled-artifact x-validator-rules for Q-51, engine-adapter.md 9.3 for Q-52) and aligning validator rule 10 with the resolver (Q-64). Q-88 needs its own decision with Q-89.
