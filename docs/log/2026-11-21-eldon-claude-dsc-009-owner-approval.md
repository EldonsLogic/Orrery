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

## Review fixes: partner Tier 3 review (sayegh9, at 3606e00)
Tests written first in `services/discovery/tests/owner_approval/test_owner_approval_partner_t3.py` (reproduced, then fixed).
- F1 High: `SealedLog.append` takes `(n, streams)` from one manifest read (`_manifest_n`) and refuses (OA-004) if its own stream moved since it was read; a competing stream commit can no longer be dropped (`test_f1_*`, k=3 reproduced OA-009 unanchored).
- F2 Medium: the summary names the company by `legalName` and `tradeName` (cap 200, schema), with label keys; a cut name blocks approval (`test_f2_*`, on `contracts/examples/blueprint-trading-minimal.json`). Test fixture moved off `company.labels`.
- F3 Medium: a confirmed approval spent by a rollback is recorded in the fold (`spent`); `review` gives `approval_spent` and approve `allowed=False`, `decide` refuses OA-018 (new code, en and ar), and a stored approval of a spent version fails the read (`test_f3_*`).
- Lows: no decision while the machine reports an apply pending or in recovery (OA-005, blocker `apply_pending`; gate status without both keys is OA-004), so `resolve_apply` is never blocked by BS-006; a rollback the gate refused with BS-003 (owner not verified) counts for nothing and may be made again, other failed rollbacks still block (`test_low_*`). Cross-linked Q-544 in Q-505, WEB-027 and README; ADR-0050 items 10 and 11 reordered.
- Results: owner_approval 161 passed; services/discovery 623 passed, 5 xfailed; build_state 188 passed; evals/tests 399 passed, 22 xfailed; check_docs, check_repo_hygiene and check_plan_independence OK.
