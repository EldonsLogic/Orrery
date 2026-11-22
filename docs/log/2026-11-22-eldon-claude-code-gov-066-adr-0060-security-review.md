# Session log: gov-066-adr-0060-security-review

Date: 2026-11-22
Author: eldon
Tool and model: claude-code / Claude Fable 5.2 (reviewer; ADR-0060 was written with Claude Opus)
Plan IDs: GOV-066

## Summary
Security review of Proposed ADR-0060 by a different model: verdict ACCEPT WITH CONDITIONS (3 High, 7 Medium, 4 Low); the conditions are written into the ADR and it is marked Accepted.

## Files touched
- `docs/security/adr-0060-security-review.md`: new. Findings with the ADR-0060 line each refers to, verdict, residual risk.
- `docs/decisions/ADR-0060-role-assignments-in-regional-store.md`: Status Accepted; Approved-by cites the review and Eldon's Q-292 decision; Decision items 6 to 15 added (writers, per-tenant keying, `syncVersion` integrity, deny on outage, no stale reads, drift, audit, staff and break-glass, residency and lifecycle, scope and order); Consequences and Supersedes updated.
- `docs/decisions/INDEX.md`: ADR-0060 row Accepted.
- `docs/open-questions.md`: Q-292 RESOLVED (applied by ADR-0060).
- `docs/PLAN.md`: GOV-066 done.

## Decisions
- ADR-0060 Accepted with conditions (Decision items 6 to 15). The direction (assignments outside the tenant site) is unchanged.
- Not verified: this is a design review; no store exists and nothing was tested. Legal points on residency are UNVERIFIED until counsel reviews them.
- Still needed before merge: the partner's review of the PR as the second founder's record (ADR-0032 item 2) and the Tier 3 human review (ADR-0035).

## Tokens or cost
Unknown.

## Next step
- GOV-065: Tool API ADR for section 4 step 2 (now unblocked).
- No plan row yet owns the store's design ADR and its security review, which ADR-0060 item 15 requires before any implementation; add one (ERP-008 and PLT-003 depend on it).
- ADR-0040 needs a deprovisioning step that deletes assignment records (ADR-0060 item 14); T53 should be re-rated when the store is designed.
- Added SEC-024 (todo) to own the store design ADR and its security review (ADR-0060 item 15). ADR-0040 deprovisioning step and T53 re-rating are follow-ups for their owners.
