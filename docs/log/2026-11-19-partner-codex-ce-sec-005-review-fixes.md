# Session log: ce-sec-005-review-fixes

Date: 2026-11-19
Author: partner
Tool and model: codex / gpt-6.1-sol
Plan IDs: CE-SEC-005

## Summary
Completed the interrupted CE-SEC-005 HTTP security suite, restored-source mutation verification and CI fixes. The row remains doing for independent re-review.

## Files touched
- `test_ce_sec_005_real_bench.py`, new `test_ce_sec_005_live_http.py`: all six proposal/apply/revert paths use real HTTP tokens; denied-role assertions distinguish the actual role guard from request/CSRF failures; policy register/unregister cover non-admin callers without forged-context parameters. Both forged role parameters are exercised too.
- Real callable inspection fixes the CE-SEC-004 string-versus-function assertion. Cross-worker policy revisions, site filtering, submit and after-submit stages, and fresh-adapter rollback are checked. Test hooks are disabled.
- Bench runner: wires both live suites, uses credential inheritance by name on host argv, reports failed cleanup, provides bounded redacted diagnostics before teardown, and unwinds on SIGTERM/SIGINT.
- CI workflows: full action SHAs and a 65-minute job budget; fast mock tests remain separate from real-bench evidence.
- `docs/architecture/change-engine.md`, plan and this log: correct stale persistence/completion claims. The existing #153 prerequisite is incorporated without merging either PR.

## Decisions
- Keep the existing mapping.py live-column-discovery fix: it is needed for the real adapter apply on the multi-column Customer DocType. The live test verifies plan auto-approval, physical column creation, preserved data and rollback through a fresh adapter; Gemini must independently review the retained production diff. The existing-column zero-statement classification quirk remains follow-up, not silently redefined here.
- Mutation tests ran only on a private synthetic bench. They temporarily restored each historical bug, expected a failing regression and restored the exact source bytes in finally blocks. No mutant is committed.
- The recovered PR still exceeds the small-PR guideline. Splitting the already-published harness/test history is deferred; this is recorded, not claimed resolved.
- Reuse-project stale-cache behavior and fully hash-locking HRMS transitive Python dependencies are not established by the clean fresh-stack runs; these remain explicit review follow-ups. No production deployment or rigid-zone logic was changed.

## Tokens or cost
Unknown.

## Next step
Gemini re-review at the pushed SHA, then founder review. CE-SEC-005 stays doing; no merge or phase exit claimed.

## Verification

- A fresh pinned Frappe/ERPNext/HRMS/MariaDB 11.4/Redis stack ran from start through verification, 15 real tests, and successful teardown. A second isolated synthetic stack ran all 15 again and was retained only for mutation checks.
- Mutation evidence: CE-SEC-001 caller-role trust, CE-SEC-002 default admin roles, CE-SEC-003 removed admin guard and CE-SEC-004 a whitelisted client-key endpoint were each detected. All five selected tests pass before mutation and again after restoration. Source files were byte-identical to their protected pre-mutation state afterward.
- Runner contract/security tests: 9 pass, including the exact missing-Frappe rejection (not an unrelated import failure), credential redaction and cleanup failure reporting.
- The proposal-only authorization inconsistency and sibling fallback findings from #153's independent review remain open. This test PR does not fix or conceal them.
- Existing deprecation warnings from engine single-DocType setters and an initial missing durable-state-table query were visible in the passing live run. No claim of production durability or multi-tenant isolation follows from this suite.
- Full outputs and mutation helpers stay outside git; no secrets, customer data or Docker artifacts are committed.
