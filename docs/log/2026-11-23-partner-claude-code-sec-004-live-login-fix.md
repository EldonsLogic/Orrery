# Session log: sec-004-live-login-fix

Date: 2026-11-23
Author: partner
Tool and model: claude-code
Plan IDs: SEC-004

## Summary
Found why the weekly live isolation workflow died in `setUpClass` with `login ... failed: HTTP 404` (run 45018521150, job 137196017488) and made the harness run the suite again: 25 tests ran locally, OK with the one known expected failure. CI result of this branch is in "Verification".

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

## Decisions
- Test the raw engine without the ERP-020 hook here; the run with the hook on stays SEC-021 (already its scope). Founders: confirm or say you want the opposite.
- No ADR: no change to auth, tenancy or contracts, only to the test bench. A security reviewer should still read `raw_engine_wsgi.py`, since it deliberately switches a guard off.

## Open questions for the founders (not written to docs/open-questions.md: not my path)
1. The adapter endpoints raise builtin `PermissionError`, so refusals are HTTP 500 with a Python traceback instead of 403 (ADR-0016, and it hides the refusal from clients). Fix in `adapter/`/`api/endpoints.py` (not my path): raise `frappe.PermissionError`; then drop the `APP_REFUSAL` branch.
2. The engine honours `X-Frappe-Site-Name` over Host. Fine behind the guard and the gateway; PLT-024 must strip it.
3. Keep this suite on the raw engine, or add a second guard-on pass now rather than in SEC-021?

## Verification
- Local, full fresh path was not run in one go: the stack was provisioned once by the runner (`--keep`) and the suite run against it with `--reuse` after each fix. Last local run: `Ran 25 tests ... OK (expected failures=1)`. One earlier run failed `test_b_jobs_invisible_to_a_rq_job_api` with "RQ Job list never showed marker" right after an engine restart and passed on the next two runs: possible flake, unexplained.
- CI: see below.

## Tokens or cost
Unknown.

## Next step
Review the PR (security reviewer for `raw_engine_wsgi.py`). SEC-021: add the guard-on pass and drop the `PermissionError` 500 accommodation once the adapter returns 403.
