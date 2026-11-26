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

## Review round 2 (gpt-6.1-sol security re-review at `9160d33`: R2, R4, R5, R6, R8, R10 closed; N1 to N5 new)
Revision 3 (Claude Opus 5.5 design sub-agent) answers N1 to N5, narrowing scope where it keeps the goal reachable:
- N1: no compiler split. A constrained field must be the only change in its authored Blueprint revision; the compiler refuses it next to anything else (`constraint_change_not_isolated`). The owner applies two separately approved revisions, the rest first; before the second the field is absent, so there is no half state.
- N2: a policy floor in the regional store, raised by policy publication before the new version activates, checked at verification and re-read under a shared row lock in the reservation transaction; unreadable refuses. Chosen over accepting a bounded window because the reservation transaction already runs in that store.
- N3: trusted provisioning rotates both `siteId` copies on every remap, clone and restore (in place included) while the site is unavailable; grants refuse while the copies differ.
- N4: caller and tenant rate first; the grant-hash budget is charged only after signature and tenant binding; test `cross_tenant_budget_poisoning_is_impossible`.
- N5: every hash uses the contract grammar `sha256:` plus 64 lowercase hex; vectors from real contract values. Storage-gating citation corrected to `engine.py:1362-1363`.
- New open point for the founders: who owns the compiler isolation check and Studio's display of the separate constraint change.

## Revision 4 (2026-11-25: Eldon's review E1 to E10, Gemini 4 Argon F1 to F4, founders' answers)
Revision 4 (Claude Opus 5.5 design sub-agent) applies the founders' three answers, which Eldon posted for both founders on PR #309, and the remaining review findings. Line numbers re-checked against main at 67660816.
- Answer 1 (no new store): the regional store and the stored policy floor are gone. The reservation, the deployment's idempotency row and the Stage 3 intent commit in one tenant-database transaction (item 12). The verifier compares the signed `siteId` with the in-site copy only; trusted provisioning is the stated assumption (item 3, E4). Withdrawing the `kid` is the emergency stop (item 4).
- Answer 2 (labels): `policyVersion` is recorded, never compared (items 2, 4, 11.2).
- Answer 3 (unique only): v1 is `unique` on `field.add` only; `relation.add`, `entity.add` and index constraints stay refused. BPL-039 (Eldon) owns `constraint_change_not_isolated` and incremental compile; the adapter re-checks the shape, including `skippedOps` (items 8, 11.6, 27).
- Other fixes: `apply_native_custom_field` and the reconcile predicate change in the constraint mode (F1, E3); only allow-listed phantom `MODIFY` (F1); pure checks before `_acquire` and side-effect-free clean refusals (F4); the eldon row split into contract and issuer rows (E6); entry-point refusals point to BPL-043 (E9); an unconsumed grant ends `failed` (E10); the NULL bench check is an acceptance condition (E8, not yet run). The ADR title and INDEX line now say "unique constraint" and "new"; Q-603 carries an update note.
- Left open: the E8 bench run itself, and the PLAN.md hunk needs a rebase onto main (E9, coordinator).

## Revision 5 (Gemini 4 Argon review of dfdbc1d1: two Medium findings)
Both findings verified against main 67660816 and fixed in ADR-0068 (Claude Opus 5.5 design sub-agent):
- Item 13 still carried the revision 3 rule that a duplicate intent with a matching binding continues. Now it follows CE-SEC-008 (`endpoints.py:1601-1617`, `schema_reconciler.py:387-405`): return the stored finalized outcome, else hold as `RECOVERY_REQUIRED` for reconcile; never continue to DDL.
- `check_ready` (`engine.py:1811-1814`, `_check_entity_refusals` `frappe_backend.py:846-883`) refuses a new `unique` field before any step, so the granted step could never run; and `execute_step` calls `_ensure_doctype_exists` (`:639`) before the checks. Now the verified grant also goes to `check_ready` on apply and admits only the one granted step; the granted path requires an existing, non-adapter-owned built-in type (`subject_missing`, `protected_subject`) and never creates one (items 10, 11.6, 19; four new tests).
