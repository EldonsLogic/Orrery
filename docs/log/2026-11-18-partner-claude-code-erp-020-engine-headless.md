# Session log: erp-020-engine-headless

Date: 2026-11-18
Author: partner
Tool and model: claude-code / sonnet-5.5
Plan IDs: ERP-020

## Summary
Made the engine headless and internal-only: a deny-by-default route allowlist (Desk, /login, website routes, unlisted API calls all get a plain 404), applied at the WSGI layer and as a `before_request` hook, plus a standalone Compose file with no published host port and internal-only networks. Unit tests and a live smoke test against a real bench pass. Row ERP-020 set to `done` for the engine-side and infra acceptance; see "Not done" for what stays with other rows.

## Files touched
- `apps/engine/change_engine/change_engine/api/route_guard.py` (new): pure `decide()` allowlist plus the `before_request` hook.
- `apps/engine/change_engine/change_engine/wsgi.py` (new): `change_engine.wsgi:application`, the same allowlist before Frappe sees the request.
- `apps/engine/change_engine/change_engine/hooks.py`: registers the hook (`before_request`).
- `apps/engine/change_engine/change_engine/tests/test_erp_020_route_guard.py`, `test_erp_020_wsgi_guard.py` (new): 30 unit tests, including a drift guard between the allowlist and the `frappe.whitelist()` endpoints.
- `apps/engine/change_engine/README.md`: two table rows.
- `infra/dev/docker/docker-compose.headless.yml` (new, standalone copy of the dev file): no ports, internal networks, token required, serves through the WSGI guard. `docker-compose.dev.yml` is NOT modified.
- `infra/dev/docker/tests/test_erp_020_headless_compose.py` (new): 9 compose-config tests.
- `infra/dev/docker/smoke_headless_engine.py` (new): live smoke test under its own project `erp020-headless-smoke`.
- `infra/dev/docker/HEADLESS.md` (new), `infra/dev/docker/README.md` (one pointer sentence).
- `docs/PLAN.md`: ERP-020 status.

## Verification
- `PYTHONPATH=. python3 -m unittest change_engine.tests.test_erp_020_route_guard change_engine.tests.test_erp_020_wsgi_guard` (apps/engine/change_engine): 30 tests OK.
- `python3 -m unittest discover -s tests` (infra/dev/docker): 26 tests OK, 3 skipped (pre-existing skips).
- `python3 infra/dev/docker/smoke_headless_engine.py`: ALL PASSED (49 checks) on a real bench (pinned image, MariaDB, Redis, site with the change engine app). From a sidecar container on the internal network: `/`, `/app`, `/desk`, `/login`, `/update-password`, `/about`, `/assets/*`, `/files/*`, `/private/files/*`, `/api/method/login`, other `/api/method/*`, `POST / cmd=...` all return 404 with no engine marker, with no token, with the token, and with token plus engine API auth. `/api/method/ping` answers 200 without a token. `/api/resource/User/Administrator` returns 200 with token plus engine API key, 404 with only the API key, 401/403 with only the token. The adapter method `get_runtime_policies` reaches the engine with token plus auth and is 404 without the token. No service publishes a host port; `engine_internal` is `Internal`. Teardown removed only the smoke project's containers, volume and networks (checked).
- Existing engine unit tests: run in a venv with pydantic 2: all pass except four that fail for reasons outside this change: `test_bpl_008` (jsonschema missing), `test_erp_006` and `test_zatca_phase1` (import `apps.*`, need repo-root path), `test_phase4_report` (one assertion failure, also fails on a clean copy of `HEAD`). Not investigated further.

## Findings
- The smoke test caught a real gap: the engine's login manager handles `/api/method/login` while building the request, before any `before_request` hook. The hook alone therefore lets a login attempt run and answers 401 with engine markers. Fix: the WSGI-level guard (`wsgi.py`), used by the headless compose file. The default dev entrypoint (`frappe.app:application`) still has that gap, so hosted environments must serve through `change_engine.wsgi:application`.
- The dev entrypoint pip-installs the mounted app at start and needs the package index, so a fully internal engine network failed to start. The headless file gives the engine an outbound-only `egress` network for the engine in dev; a hosted image should bake the app in and drop it.

## Decisions
- None needing an ADR. Choices for the founders to confirm in the PR: (1) the record API (`/api/resource/*`) is allowed for token holders per Frappe permissions, not per doctype, because the adapter's real HTTP surface is not defined yet (the in-tree adapter runs in-process); narrow it with OPR-003. (2) Whether to drop the loopback port from `docker-compose.dev.yml` once ERP-002 and the phase 0 proofs stop using it. (3) Shared secret `X-Internal-Token` as the internal-caller proof, on top of the network boundary.

## Not done or not verified
- Gateway side (PLT-024, other agent): adding `X-Internal-Token`, stripping client copies, path rewriting, header and cookie handling. Requests are listed in HEADLESS.md. No gateway code touched.
- `docker-compose.dev.yml`, `run_50_tenant_load_spike.py` and `test_erp_002*` untouched; ERP-002's bench (`erp002-load-spike`) was running and was not touched.
- A hosted image with the app baked in and no `egress` network: not built. Production placement, TLS and rate limiting: other rows.
- Staging crawl for engine markers (ADR-0016 enforcement item): not part of this row.
- Other API ports (socket.io realtime): not part of today's bench; documented as must-not-be-public.
- Allowed responses (e.g. the 200 ping, record API) still carry whatever headers the engine and gunicorn add; stripping them is PLT-024.

## Tokens or cost
Unknown.

## Next step
PLT-024: gateway sends and strips `X-Internal-Token`, serves only our own paths. OPR-003: pin the adapter's HTTP surface and narrow the record API allowlist. Hosted engine image without `egress`.
