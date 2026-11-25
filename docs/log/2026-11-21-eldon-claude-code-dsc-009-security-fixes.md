# Session log: dsc-009-security-fixes

Date: 2026-11-21
Author: eldon
Tool and model: claude-code / opus-5.5 (subagent); review by fable-5.2
Plan IDs: DSC-009

## Summary
Fixed the Fable Tier 3 security review findings on #224 with 13 tests written first: H1 outcome records checked against the folded log (one outcome per decisionSeq, same clock-skew rule), H2 approval blocked (OA-017 too_large) when any summary list is cut, cap 200, security-relevant item fields shown, plain notice; M4 same quote digest stays current after expiry past draft; M5 sealed log behind a store port, no store refuses (OA-010) outside tests; L7 to L9.

## Files touched
- services/discovery/ owner approval package, labels.json (en and ar), README
- services/discovery/tests/owner_approval/test_owner_approval_tier3.py: new
- docs/open-questions.md: Q-544 (deferred M3)

## Decisions
- None new; M3 deferred to Q-544, L6 stays Q-524, store rollback anchor stays Q-521.

## Tokens or cost
About 160k tokens (subagent).

## Next step
Fable re-review of the fixes; partner line-by-line review (Tier 3). Tests: services/discovery/tests 589 passed, 5 xfailed; build_state 187 passed.
