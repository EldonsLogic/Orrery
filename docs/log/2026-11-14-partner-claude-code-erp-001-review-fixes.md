# Session log: erp-001-review-fixes

Date: 2026-11-14
Author: partner
Tool and model: claude-code (Claude Opus 5.5)
Plan IDs: ERP-001

## Summary
Applied Eldon's review of PR #39: the live verifier now has the HTTP check its test expects, CI runs the bench tests, the README states the spike's limits, and this log corrects the earlier logs' claims.

## Files touched
- `infra/dev/docker/verify_dev_bench.py`: new HTTP check. It asks for `/api/method/ping` on `127.0.0.1:${ENGINE_PORT}` (default 8000), sends the site as the Host header, and fails with "HTTP endpoint is not ready". The live test `test_site_with_unreachable_http_port_cannot_pass_verification` expected this check, but it did not exist.
- `.github/workflows/ci.yml`: new `dev-bench-tests` job runs `infra/dev/docker/tests`. The live and networked-build tests skip on CI because no bench runs there.
- `infra/dev/docker/README.md`: three additions.
  - The verifier's HTTP check.
  - A dev-only warning that `bench new-site` carries the passwords as process arguments inside the container.
  - A "Known limits" section: HRMS transitive Python dependencies are not locked or hashed, and there is no worker, scheduler or socketio service, so background and scheduled jobs never run.
- `infra/dev/docker/Dockerfile`, `infra/dev/docker/entrypoint.sh`: the working name is replaced by "the platform".

## Evidence (this machine, synthetic data only)
- Against the running bench (`ENGINE_PORT=18111`), the verifier passes. It now prints "apps, versions, HRMS commit, Redis and HTTP".
- With `BENCH_LIVE_PROJECT` set to the running project, `python3 -m unittest discover -s tests` in `infra/dev/docker` ran 15 tests: OK, 1 skipped (the networked image-build check). Both live verifier tests pass, including the HTTP one.
- Without a bench: 15 tests, OK, 3 skipped.

## Corrections to earlier logs (logs are append-only, so they are corrected here)
- `2026-11-07-partner-antigravity-dev-bench-pin.md` is superseded on these points:
  - It says Q-6 and Q-15 were marked resolved. Both are still open in `docs/open-questions.md`.
  - It gives the Frappe source commit `53bae3ef…` as fact. That commit is UNVERIFIED (`apps/engine/README.md` says so). Only the HRMS commit is enforced by the build.
  - It gives the Redis licence as BSD-3-Clause without a label. The licence register now cites the upstream source licence and marks the image contents and legal reading UNVERIFIED, pending counsel (Q-15).
- Test counts:
  - The PR body and the first evidence line of `2026-11-14-partner-claude-code-erp-001-bench-proof.md` say 14 tests. That was before `test_links_built_assets_into_sites` was added.
  - The suite has 15 tests, as the follow-up section of that log says.
  - The PR body is updated to 15.
- Force-with-lease in `2026-11-11-partner-codex-erp-001-rebase.md`:
  - The rebase rewrote the history of the partner's own unmerged PR branches and was pushed with `--force-with-lease`. The partner authorised it in that session, as that log records.
  - AGENTS.md says "No force-push, no history rewrite", so the push broke the written rule even though nobody else had commits on those branches.
  - The partner's explicit acceptance, or a rules note allowing it, is still owed. It is a founder statement, not something this session can give.
  - From now on, the stack is updated by merging the lower branch into the upper one. No rebase and no force-push.

## Decisions
- None.

## Tokens or cost
Unknown.

## Next step
Eldon re-reviews #39 (ERP-001). The partner records acceptance of the force-with-lease, or a rules note, in the next log.
