# Session log: bpl-036-design-confirmations

Date: 2026-11-21
Author: eldon
Tool and model: claude-code
Plan IDs: BPL-036

## Summary
Decided 19 of 31 "confirm" rows from docs/open-questions.md (compiler, token resolver, Studio, migration) in one ADR, ADR-0057 (Proposed, partner review pending). No code changed. Revised after a cross-model review (Fable) of the first commit.

## Files touched
- docs/decisions/ADR-0057-compiler-and-studio-design-confirmations.md: new ADR, decision table with file:line rationale.
- docs/decisions/INDEX.md: ADR-0057 row.
- docs/open-questions.md: 16 rows RESOLVED, 3 rows DECIDED (open until BPL-037 or BPL-038 lands); Q-178 and Q-254 given their missing Owner, Needed by and Related cells (text unchanged).
- docs/PLAN.md: BPL-036 (doing until partner review), BPL-037 and BPL-038 (todo).

## Decisions
- [ADR-0057](../decisions/ADR-0057-compiler-and-studio-design-confirmations.md).
- Keep (RESOLVED): Q-50, Q-55, Q-56, Q-58, Q-60, Q-66, Q-67, Q-68, Q-70, Q-71, Q-72, Q-75, Q-78, Q-81, Q-82, Q-86.
- Decided, open until the plan row lands: Q-51 and Q-52 (BPL-037, contract patch), Q-64 (BPL-038, validator rule 10 uses the resolver's derive).
- Excluded, left open:
  - Q-54: puts a forward-reference obligation on the partner's adapter that the contract does not state; needs contract text and partner agreement.
  - Q-59: ledger or tax risk classification.
  - Q-69: Cf characters (bidi, zero-width) still accepted; deferred to Q-93 (security).
  - Q-73: a stored `resolved` block skips the contrast guardrail; needs the server-only write rule (Q-63) and a save-path row.
  - Q-74: tenant slug source is a tenancy question.
  - Q-79: auto-granted approvals touch approval authority (ADR-0048, ADR-0049).
  - Q-80: ZATCA QR inputs are e-invoicing.
  - Q-83, Q-84, Q-85: injection suite is security; Q-84 depends on PLT-009, Q-85 on a real adapter.
  - Q-88: unsure; the Blueprint schema file is 0.4.0 while meta.schemaVersion and the migrator are 0.1.0, so the row's premise fails on main (tied to Q-89).
  - Q-93: confusable handling is untrusted-content defence (security).

## Tokens or cost
Unknown.

## Next step
Partner review of ADR-0057, then BPL-036 to done. BPL-037 and BPL-038 are ready. Update docs/architecture/blueprint-versioning.md:27 (still calls Q-86 open). Q-88 needs its own decision with Q-89.
