# Session log: sec-004-live-login-fix

Date: 2026-11-23
Author: partner
Tool and model: claude-code
Plan IDs: SEC-004

## Summary
Found why the weekly live isolation workflow died in `setUpClass` with `login ... failed: HTTP 404` (run 45018521150, job 137196017488) and made the harness run the suite again: 25 tests ran locally, OK with the one known expected failure. CI run 45086223077 on this branch: success.

## Root cause (reproduced locally, not a race)
- The ERP-020 hook `before_request = ["change_engine.api.route_guard.enforce_internal_only"]` (`hooks.py`) is active on every site that has change_engine installed, and the harness provisions A, B and the twin with it. The hook answers a plain 404 to everything outside its internal allowlist: GET ping, the adapter POST methods and GET on four business doctypes, all with an internal token. `/api/method/login`, session cookies, `/api/resource/ToDo`, files, backups and the job API are not on it.
- Evidence: against the kept stack, `POST /api/method/login` on site A with a wrong password returned 401 (the login manager runs before `before_request` hooks) and with the real password returned 404 from the hook. After `remove-from-installed-apps change_engine` on site A the same login returned 200 and `get_logged_user` returned Administrator. Provisioning took about 4 minutes in CI (11:42 engine up, 11:46 test start), so this was never a readiness race. The INF-015 Redis change (d1d30f0) was not involved: the stack came up and all three sites provisioned.
- The guard is correct; no supported way exists to log in through it, so the suite cannot "authenticate the supported way". The suite certifies the engine's own isolation and attacks it through exactly the routes the hook hides. With the hook on, every `DENIED` assertion would pass on the blanket 404 and every positive control would fail.

## Files touched
- `infra/dev/docker/isolation/raw_engine_wsgi.py` (new): test-only WSGI module that filters the one ERP-020 hook out of `frappe.get_hooks("before_request")`, and serves `/files` and `/assets` as `bench serve` does (bare gunicorn does not; a proxy would). It refuses to start unless `SEC004_RAW_ENGINE=1` and the compose project name contains `sec004`. The hook, the allowlist, the production image and the headless compose file are untouched.
- `infra/dev/docker/isolation/docker-compose.isolation.yml`: engine service runs gunicorn on that module (same settings as the dev entrypoint `start`) and mounts it read-only. The mount path is relative to `infra/dev/docker`, the first compose file.
- `infra/dev/docker/isolation/README.md`: says so.
- `apps/engine/change_engine/change_engine/tests/live_sec_004_bench_attacks.py`: three assertion changes that the engine's real behaviour forced, each found by the first full run once login worked (6 and 9 of the 25 tests failed before them):
  1. `X-Frappe-Site-Name` is the engine's site selector and overrides Host (`frappe/app.py` `init_request`). The old assertions assumed it is ignored. That is why the guard refuses the header and why the gateway must strip it (PLT-024). The test now pins the behaviour and keeps what matters: credentials stay bound to the site the header names, B's credentials fail there, and A's credentials never return B's marker. `X-Forwarded-Host` keeps the original strict assertions.
  2. The adapter refuses with the builtin `PermissionError`, which the engine reports as HTTP 500 with a traceback. `assert_refused` accepts `DENIED` or a 500 whose body contains `PermissionError: Not permitted`; any other 500 still fails. The no-leak checks are unchanged.
  3. Public file controls needed the `/files` serving above.
  4. Found by CI run 45083756451 (24 of 25 passed; the known-leak test showed `unexpected success`, reproduced on a fresh local stack): the engine's RQ Job list ignores `limit_page_length` and `start` and returns one fixed page of 20 jobs in queue and status order, so a site's own background jobs push the twin's job (and B's positive-control job) off the page. The twin leak check, B's positive control and A's no-leak check now scan every (queue, status) bucket through the `filters` parameter; the twin check fails, rather than passes, if a bucket is full.

## Decisions
- Test the raw engine without the ERP-020 hook here; the run with the hook on stays SEC-021 (already its scope). Founders: confirm or say you want the opposite.
- No ADR: no change to auth, tenancy or contracts, only to the test bench. A security reviewer should still read `raw_engine_wsgi.py`, since it deliberately switches a guard off.

## Open questions for the founders (not written to docs/open-questions.md: not my path)
1. The adapter endpoints raise builtin `PermissionError`, so refusals are HTTP 500 with a Python traceback instead of 403 (ADR-0016, and it hides the refusal from clients). Fix in `adapter/`/`api/endpoints.py` (not my path): raise `frappe.PermissionError`; then drop the `APP_REFUSAL` branch.
2. The engine honours `X-Frappe-Site-Name` over Host. Fine behind the guard and the gateway; PLT-024 must strip it.
3. Keep this suite on the raw engine, or add a second guard-on pass now rather than in SEC-021?

## Verification
- Local, full fresh path was not run in one go: the stack was provisioned once by the runner (`--keep`) and the suite run against it with `--reuse` after each fix. Last local run: `Ran 25 tests ... OK (expected failures=1)`. `test_b_jobs_invisible_to_a_rq_job_api` failed twice on the reused stack with "RQ Job list never showed marker": the same 20-row page cause (item 4), fixed; four later runs on that stack passed.
- CI run 45083756451 (first push of this branch): 24 of 25 passed, `test_prefix_twin_jobs_invisible_to_a` showed unexpected success (item 4 above). Run 45086223077 (fresh path, after that fix): success, 25 tests, `OK (expected failures=1)`.

## Tokens or cost
Unknown.

## Next step
Review the PR (security reviewer for `raw_engine_wsgi.py`). SEC-021: add the guard-on pass and drop the `PermissionError` 500 accommodation once the adapter returns 403.

## Review fixes, round 1
Cross-model review (ChatGPT gpt-6.1-sol) at 08e7f73 asked for changes; four findings, each fixed without weakening a check.
1. Medium, inconclusive scan left CI green: the full-bucket and positive-control failures sat inside the `expectedFailure` test, so they counted as the expected failure. The prefix-twin check is now its own class `PrefixTwinJobLeak`: the positive control on T and the complete enumeration of A's buckets run in `setUpClass` (a failure there is an error, never an expected failure); only the SEC-021 leak assertion over the stored scan is `@expectedFailure`. A plain test pins that all 21 buckets were scanned. The harness moved to a shared `LiveBench` base so both classes use it.
2. Medium, no saturation check on the ordinary B-job scan: `rq_job_buckets_as` now rejects a full page (20 rows) or an unparseable page for every scan, so 20 legitimate A jobs can no longer hide a leaked B job at position 21. Only the positive-control poll for a marker opts out (`require_complete=False`), because finding the marker is conclusive.
3. Medium, substring match for the refusal: `is_app_refusal` parses the JSON error body and checks only the final exception line (last traceback in `exc`, else `exception`) against `PermissionError: Not permitted`; an unrelated final exception whose chained traceback mentions the refusal no longer passes.
4. Low, `sec004` substring in the project check: new `infra/dev/docker/isolation/sec004_project.py` holds one rule, `^sec004([-_][a-z0-9]+)*$` (exactly `sec004` or `sec004-...`; the default `sec004-isolation` and CI `sec004-ci-isolation` match, `prod-sec004` and `sec004prod` do not). The runner and `raw_engine_wsgi.py` both use it; the compose file mounts it next to the wsgi module. README updated.

Offline tests: `apps/engine/change_engine/change_engine/tests/test_sec_004_live_helpers.py` (11 tests, standard library only): chained-traceback refusal body, quoted-refusal body, last traceback decides, `exception` field, non-JSON; full and unparseable RQ page; accepted and refused project names. Against the old code the helper tests fail (the helpers did not exist; the old substring check accepts the chained body, asserted in the test) and the project-name test fails on `prod-sec004`, `sec004prod`, `shared-sec004-isolation`, `sec004-`. They pass now. They run as a first step of `sec-004-live-isolation.yml`. Not wired into `tests.yml` (PR CI): that file is outside this task's allowed paths; one line there would do it.

Verification of round 1: CI run 45088110814 (workflow_dispatch on 55fe175, fresh path): offline helper tests 11 OK, live suite `Ran 26 tests ... OK (expected failures=1)`; the prefix-twin leak still shows as the one expected failure and the scan-coverage test passes.
