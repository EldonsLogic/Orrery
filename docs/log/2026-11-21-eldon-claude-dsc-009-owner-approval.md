# Session log: dsc-009-owner-approval

Date: 2026-11-21
Author: eldon
Tool and model: claude
Plan IDs: DSC-009

## Summary
Built the owner approval flow (draft to owner_approved) as a service and view model with a sealed decision log, bound to the Blueprint and quote digests; Tier 3 (approval authority), needs line-by-line human review.

## Files touched
- services/discovery/owner_approval/: flow, sections (summary, cost, gaps, test month), sealed ledger, ports, text cleaning, labels (en, ar), README
- services/discovery/tests/owner_approval/: 89 tests (mapped by services/discovery/tests/*)
- docs/PLAN.md: DSC-009 done, WEB-027 added (web screen follow-up); docs/open-questions.md: Q-520 to Q-526

## Review round 1 (PR #224)
- Machine amended (ADR-0050 item 11, BPL-020): `owner_approvals` port, `approve_owner(expected_digest, quote_digest)`, re-check at every later gate, `status.owner`; machine tests updated with a fake port plus services/blueprint/tests/build_state/test_bs_owner_approval.py.
- Flow: `verify` port, one step-up per decision, refused gate call not a decision (retry), clock skew tolerance per record, summary covers approvals, integrations, assistants, locations and compliance, reject/request changes in any pre-live state, multi-owner rule, reconcile per owner, labels and text fixes. Q-540 to Q-542; Q-520 and Q-522 resolved.

## Decisions
- None new; follows ADR-0047, ADR-0048, ADR-0050. Open questions Q-520 to Q-526 (step-up twice, shared sealed log, machine takes no approval evidence, several owners).

## Tokens or cost
Unknown or approximate, if known.

## Next step
WEB-027 (screen) after the host adapters (Q-505); QA-009 end-to-end rehearsal. An integration test against the real machine waits for the adapters.
