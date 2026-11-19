# Session log: ce-sec-005-review-guard

Date: 2026-11-19
Author: partner
Tool and model: codex / gpt-6.1-sol
Plan IDs: CE-SEC-005

## Summary
Closed the new Low finding from the independent re-review of PR #134: both live suites now have the same offline, fail-closed and no-mock CI guards. CE-SEC-005 remains doing.

## Files touched
- `infra/dev/docker/tests/test_ce_sec_005_real_bench_ci.py`: scan both live suites for mock/simulator use; run each module independently to verify a clean offline skip and the exact missing-Frappe failure when the real-bench flag is required. Subtests identify the affected module.
- This new session log records the review disposition and prerequisite merge order.

## Decisions
- [Gemini re-review](https://github.com/EldonsLogic/Orrery/pull/134#issuecomment-6993535541) verified all three High findings fixed at `60bc051889ee410eef4a5b10be4813839ea903e0`; eight original findings are fixed and three remain partial. Accessed 2026-11-19.
- [PR #153](https://github.com/EldonsLogic/Orrery/pull/153) is still open at `fa06baf5d57a5872f1ef907dc5c02ba81dbe842e` as checked on 2026-11-19. Its production fixes are prerequisites for the HTTP regressions. Merge #153 first, then obtain Eldon's review of #134, including the shared workflow edits. No merge is authorized or performed in this session.
- Keep the documented sibling authorization gaps, two-site provisioning proof, reused-project cache behavior, Redis healthchecks, mapping no-op classification, transitive dependency locking and oversized PR as explicit follow-ups. This test-only follow-up does not close those areas or any phase exit.

## Verification

- Reproduced the gap: adding a temporary `from unittest import mock` import to the HTTP suite passed the old no-mock guard.
- The same mutation fails the revised guard in the HTTP suite's subtest. Exact source bytes were restored in a finally block; no mutant is committed.
- All 9 runner contract/security tests pass after restoration, including separate offline and required-runtime checks for both modules.
- No live Docker bench was rerun for this test-only change. The independent re-review records prior live CI and mutation evidence at the reviewed head; new-head CI is pending when this log is written.

## Tokens or cost
Unknown.

## Next step
Check CI for the pushed follow-up, merge the prerequisite #153 through founder review, then obtain Eldon's #134 review. Keep CE-SEC-005 doing until sign-off and the applicable exit evidence exist.
