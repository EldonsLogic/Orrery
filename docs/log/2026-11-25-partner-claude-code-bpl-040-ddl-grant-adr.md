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
