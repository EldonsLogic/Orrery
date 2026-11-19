# Session log: ce-sec-005-opus-review-nits

Date: 2026-11-19
Author: partner
Tool and model: codex / gpt-6.1-sol
Plan IDs: CE-SEC-005

## Summary
Addressed Eldon's Opus review of PR #134: merged current main after prerequisite #153, changed the scheduled bench run to weekly, reduced the CI and runner budgets together, and reconciled the security status documentation. CE-SEC-005 remains doing pending fresh CI and acceptance.

## Files touched
- `.github/workflows/real-bench.yml`: weekly Monday UTC schedule and a 25-minute job limit; path filtering and manual dispatch retained.
- `infra/dev/docker/run_real_bench_ci.py`: five-minute startup, provisioning and test limits; two-minute readiness, verifier and teardown limits. The normal path's nominal phase limits, including failure diagnostics, total 22.5 minutes, with polling/setup headroom inside the job limit.
- `docs/architecture/change-engine.md`: CE-SEC-002's targeted rollback/session fixes are marked fixed in merged #153; sibling role-default and proposal-authorization follow-ups stay explicit.
- This log. The main merge introduces no conflict resolution or new changes to the other founder's code.

## Decisions
- [Eldon's Opus review](https://github.com/EldonsLogic/Orrery/pull/134#issuecomment-7006579483) approves with nits and no High findings. [Prerequisite #153](https://github.com/EldonsLogic/Orrery/pull/153) merged before this update. Accessed 2026-11-19.
- Merged current main at `f3cf06c`; #153's endpoint, rollback and caller-role test changes no longer appear in this PR's diff. The remaining production change is `adapter/mapping.py`: pass `existing_columns_desc=None` to inspect actual live columns instead of inventing a standard-column snapshot. It remains called out in the PR description and covered by the existing live multi-column Customer apply/rollback test.
- The PR remains larger than the small-PR guideline after removing the prerequisite diff. Rewriting the published review history or moving the already-reviewed suites is not part of this follow-up.
- Retain the documented HRMS installation flakiness risk, limited synthetic-log redaction, reused-project behavior, two-site proof and dependency-locking follow-ups. No branch protection or required-check setting is changed; the real-bench job remains path-filtered.

## Verification

- Docker runner/bench contracts: 26 tests, 23 pass and 3 live/network skips; includes all 9 real-bench CI guard tests.
- Fast engine security suites: 54 pass and 22 subtests pass after the main merge.
- [Previous live CI job](https://github.com/EldonsLogic/Orrery/actions/runs/44414700253/job/135191793126) at `791fe3d` succeeded; its recorded job duration is 3 minutes 1 second. Accessed 2026-11-19. This supports the tighter budget but does not establish that the recorded transient HRMS install failure cannot recur.
- No new local live stack was created. The pushed update must run the real-bench job under the shorter limits; new-head CI is pending when this log is written.

## Tokens or cost
Unknown.

## Next step
Verify fresh repository and real-bench CI at the pushed head. Keep the existing Vercel team-access issue visible, then return the reviewed PR for acceptance; CE-SEC-005 stays doing until acceptance. No merge or phase exit claimed here.
