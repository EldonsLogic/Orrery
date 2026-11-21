# Session log: bpl-020-build-state-machine

Date: 2026-11-21
Author: eldon
Tool and model: claude
Plan IDs: BPL-020

## Summary
BPL-020 (Tier 3): build state machine draft to live with sealed log, re-derived evidence, human-only step-up gates, write-ahead idempotent applies and the sealed sign-off ledger (Q-274).

## Files touched
- services/blueprint/build_state/: machine, sealed log, ledger, ports, labels (en, ar); tests moved to services/blueprint/tests/build_state/ so CI runs them (157)
- docs/decisions/ADR-0050-build-state-machine.md and INDEX.md; docs/open-questions.md (Q-500 to Q-506); docs/PLAN.md (BPL-020 done)

## Decisions
- [ADR-0050](../decisions/ADR-0050-build-state-machine.md) (Proposed). Order follows the contract, not the plan-row shorthand (Q-500).

## Tokens or cost
Unknown.

## Next step
Other-founder line-by-line review and a different-model security review (Tier 3). Then host adapters for the identity, review and engine ports (Q-505), DSC-009 on top, QA-009 rehearsal. Not verified: no integration test through the real ReviewQueue (needs wiring, Q-432).

Review round 1 (Opus): fixed H1 (tests under the CI-mapped path), H2 (revision plus digest binding), H3 (single-flight applies, lease, reconcile), M1 (queue item derived), M2 (rollback to draft only), M3 (recovery), M4 (reconcile), M5 (audit actor), L1, L4, L5 partly. Q-510 to Q-513 added.
