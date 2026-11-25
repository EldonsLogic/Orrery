# Session log: bpl-040-ddl-grant-adr

Date: 2026-11-25
Author: partner
Tool and model: claude-code (Claude Opus 5.5 child wrote the ADR; Opus 5.5 coordinator applied it)
Plan IDs: BPL-040

## Summary
ADR-0068 (Proposed) answers Q-603 as the partner decided: a signed (ed25519, KMS key, public key only in the adapter), single-use, scope-bound DDL-constraint grant lets the guarded field path add a unique or index constraint to an adapter-owned custom field on an allow-listed built-in engine type (Customer and Supplier to start), on one audited code path in `guarded_apply/`. Design only; no code before the ADR is Accepted and security-reviewed. Until then such fields stay refused with `unique_or_index`.

## Files touched
- `docs/decisions/ADR-0068-ddl-gate-approval-pass-through.md`: new, Proposed.
- `docs/decisions/INDEX.md`: one row.
- `docs/PLAN.md`: BPL-040 set `doing`.

## Decisions
- ADR-0068 Proposed. Open for founders: the starting allow-list, the table row ceiling, whether the approver must differ from the requester for this gate, MFA step-up for production grants. Follow-up rows named in the ADR (not added here): partner build in `apps/engine/`; Eldon contract field `approvals.ddlConstraintGrant` and the issuer; shared `S24` key in the secrets inventory and threat model.

## Tokens or cost
Unknown.

## Next step
Security review by a different model (gpt-6.1-sol), then Eldon's line-by-line review (Tier 3: auth and secrets). Bench facts marked UNVERIFIED in the ADR (empty-value storage in a unique Data column, ALTER atomicity on failure) must be proven by the build row.

## Review round 1 (gpt-6.1-sol security review at `c31042e`: REQUEST_CHANGES, R1 to R11)
Revision 2 (Claude Opus 5.5) answers all eleven findings, by narrowing scope where simpler:
- R1: v1 allows one step adding one constraint to one new field; one scope entry, one reservation per operation. R6: Data or Link without a default only. R8: existing-column cases out of v1.
- R2: the unmapped `entity.add` branch and `_ensure_doctype_exists` refuse `unique` and `indexed` fields with or without a grant; every `execute_step` entry point listed. This bypass exists on main today, so the entry-point refusals go in the partner G1 row now, not with the integration.
- R3: grants issued only at the approved-to-executing transition, bound to the idempotency key and policy version; `minPolicyVersion`, `kid` withdrawal, 300 s lifetime, expiry rechecked at consumption. R4, R5: durable baseline, plan and dispatch journal; derived deployment ids; strict intent insert; failed lookups block. R7: signed `siteId` and `aud`. R9: verified lock timeout, bounded count, attempt budget. R10: verifier-only partner G1 row, Eldon G1 contract and issuer row, partner G2 integration row. R11: one `ddlg1.` format with one strict parse.
- New open points for the founders: owners of the compiler split and the `siteId` rule in clone and restore tooling; whether an approval returns to `approved` when its grant expires unused; a separate row for today's deploy-path defects.
