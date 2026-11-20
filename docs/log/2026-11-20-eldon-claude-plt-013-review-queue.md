# Session log: plt-013-review-queue

Date: 2026-11-20
Author: eldon
Tool and model: claude / sonnet-5.5
Plan IDs: PLT-013

## Summary
Built the human review queue and the `team_reviewed` gate evidence (Tier 3, approval authority) under `services/control-plane/reviewqueue/`, in the eldon lane (the control plane, not the partner's gateway or provisioning paths).

## Files touched
- services/control-plane/reviewqueue/: queue, canonical digest and input checks, errors, `checklists.json`, `labels.json` (en and ar)
- services/control-plane/tests/reviewqueue/: 65 tests covering tampered or forged stored records, stored verdict, plain-hash seal, no key, cross-tenant, iterator and set input, floats, time bounds and regression, duplicates, stale content, hold (quarantine), separation of duties (author, involved, attester, linked person), step-up, audit hash and length
- docs/decisions/ADR-0049-human-review-queue.md (Proposed), INDEX.md; docs/open-questions.md (Q-440 to Q-446); docs/PLAN.md (PLT-013 done); services/control-plane/README.md

## Decisions
- ADR-0049 (Proposed, Tier 3: needs the other founder's line-by-line review and a different-model security review). Evidence only: the queue never changes a build state.

## Tokens or cost
Unknown.

## Next step
BPL-020 reads `gate_evidence` and re-reads stored content itself; DSC-009 follows. Console screens for the queue (PLT-014 or a follow-up row). Open: Q-440 to Q-446.

## Review follow-up (PR 219)
Fixed the Opus review: H1 (non-empty involved for request and sign-off kinds, union on resubmit, required `linked_staff`), H2 (sealed per-item head and queue manifest, tail cut, rollback, deletion and rehash fail closed), M1 (sealed submission number orders items), M2 (host clock only), M3 (a step-up decides once), M4 (`hold_item`), M5, and the LOWs (random ids, surrogates, claims on reads, size cap, invalid rows, RQ-002 on regression). 93 tests; mutations of the head check, the union, the step-up spend, the ordering and the involved rule each fail tests. New Q-480 to Q-486.
