# Session log: sec-024-role-store-design

Date: 2026-11-22
Author: eldon
Tool and model: claude-code (Claude Opus, subagent of the orchestrator session)
Plan IDs: SEC-024

## Summary
Wrote the design ADR for the regional role-assignment store (ADR-0061, Proposed) that ADR-0060 item 15 requires, mapping each ADR-0060 condition (items 6 to 14) to a design point. Stacked on the GOV-066 branch (PR #269).

## Files touched
- docs/decisions/ADR-0061-role-assignment-store-design.md: new, Proposed.
- docs/decisions/INDEX.md: ADR-0061 row.
- docs/PLAN.md: SEC-024 set to `doing` (it goes to `done` only after its security review by a different model).
- docs/open-questions.md: Q-580 to Q-583 (numbers chosen above Q-563, the highest used on any origin branch, to avoid collisions with open PRs).
- docs/log/2026-11-22-eldon-claude-code-sec-024-role-store-design.md: this log.

## Decisions
- ADR-0061 (Proposed): one store per served country in its own database with three credentials (reader, writer, bootstrap), none of them `S22`; per-tenant keys, row-level security and `S10b` encryption bound to tenant and member; store-allocated `syncVersion` in the write transaction; signed snapshots; restore fencing against an off-box anchor; writes only as executions of approved `AP-PERM-01` requests plus a once-only bootstrap; no cache; deny on every failure; history table as the hash-chained audit trail. Needs a security review by a different model and both founders before Accepted.

## Tokens or cost
Unknown.

## Next step
- SEC-024: security review of ADR-0061 by a different model (Fable or another non-Opus model); founder answers to Q-580 to Q-583.
- Follow-ups named in ADR-0061 Consequences: GOV-065 (Tool API wording), a contract ADR for the signed `sync_members` snapshot, SEC-002 credential and signing-key ids, ADR-0040 deprovisioning step for assignment rows (partner), SEC-008 off-box anchor, INF-001 hosting.

## Revision after round 1 security review (Claude Fable 5.2, REVISE)
- Review: 3 High, 9 Medium, 6 Low, 14 test additions. ADR-0061 rewritten (not appended) where the text contradicted itself; Status stays Proposed.
- R-H1: role changes need two identity-signed human assertions (initiate, approve) bound to the payload hash with step-up time; the evaluator's record is evidence only; the ADR states that a compromised write service can grant roles and that the verifier detects it.
- R-H2: anchor defined (in-country, separate account and credentials, append-only, conditional append per `seq`); anchor-before-effect inside the write transaction; resume above the maximum of anchor, store and adapter; adapter refuses a lower `generation`.
- R-H3: restore reconciliation is a deterministic replay of the anchored chain only; humans approve or refuse, never edit. Catalog refresh listed as a write outside `AP-PERM-01` with its own constraints.
- Mediums and Lows: encryption in the service with a split of database and service checks; bootstrap rule made satisfiable; single-use approvals and compare-and-set; signed rows and state, column and version in associated data, latest-history check per read; forced row-level security, transaction-local tenant, separate per-tenant assignment key; promotion bound to signed receipts; tombstones, last-Owner rule, signed deletion evidence; audit reader role; rate-limited refusal log; snapshot expiry; owner and admin from catalog flags.
- Tests: RAS-T01 to RAS-T22. Q-581 and Q-582 reworded and marked as blockers for acceptance.
- Next: re-review by a different model; founder answers to Q-581, founder and counsel answers to Q-582.
