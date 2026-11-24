# Headless engine: internal-only network (ERP-020, ADR-0016)

Status: development
Owner: partner
Plan ID: ERP-020

The engine is never a customer-facing web server. Two independent layers enforce it.

## Layer 1: network (primary)
`docker-compose.headless.yml` is a standalone copy of `docker-compose.dev.yml` (same pins, volumes and build) without the host port; a test keeps the two in step (it is not an override because Compose's `!reset` tag, needed to drop a port, fails the repo's YAML check):
```bash
export COMPOSE_PROJECT_NAME=platform-headless SITE_NAME=synthetic.localhost
export ENGINE_INTERNAL_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
# plus DB_ROOT_PASSWORD and ADMIN_PASSWORD as in README.md
docker compose --env-file /dev/null -f infra/dev/docker/docker-compose.headless.yml up -d --build
```
- No service publishes a host port. The engine listens on 8000 inside the project only.
- Two networks are `internal: true` (no route to the host or the internet): `data` (database, caches, engine) and `engine_internal` (engine and its callers). The database and caches are not on `engine_internal`.
- Dev only: the engine is also on `egress` (outbound, no published port) because the dev entrypoint pip-installs the mounted app at start and needs the package index; found while running the smoke test on a fully internal network. A hosted image bakes the app in and drops `egress`.
- The gateway is the only ingress. It runs in its own Compose project or file, joins the external network `<project>_engine_internal` and reaches the engine at `engine:8000`, sending the site name in the `Host` header. Only the gateway publishes a port to the outside.
- Anything hosted (shared dev server, staging, production) must use this shape. `docker-compose.dev.yml` alone still publishes the engine on IPv4 loopback for local verification (`verify_dev_bench.py`, phase 0 proofs); that is a developer convenience, not a deployment shape. Open for the founders: drop the loopback port from the dev default once ERP-002 and the proofs no longer need it.
- Do not run the realtime (socket.io) service on a public port either; it is not part of the bench today.

## Layer 2: engine route guard (defence in depth)
The allowlist lives in `apps/engine/change_engine/change_engine/api/route_guard.py` and is applied twice:
- `change_engine/wsgi.py` (`gunicorn change_engine.wsgi:application`, set by the headless compose file): runs before the engine sees the request. This is required, not optional. The smoke test showed that the engine's login manager handles `/api/method/login` while it builds the request, before any `before_request` hook, so the hook alone still lets a login attempt run and answers 401 with engine markers. The default dev entrypoint (`frappe.app:application`) has that gap; hosted environments must use the WSGI entry. The WSGI layer reads the token from `ENGINE_INTERNAL_TOKEN` only and checks `cmd` in the query string.
- A `before_request` hook in `hooks.py`: second layer, also checks `cmd` in form and JSON bodies and the site-config token. It denies every request unless it matches the allowlist, with a plain 404 that carries no engine marker and no cookie.

| Caller | Allowed |
|---|---|
| Anyone | `GET`/`HEAD /api/method/ping` (liveness) |
| Holder of the internal token (header `X-Internal-Token`) | `POST /api/method/change_engine.api.endpoints.<adapter method>` (twelve whitelisted methods) and the record API: `GET`/`POST /api/resource/<DocType>`, `GET`/`PUT`/`DELETE /api/resource/<DocType>/<name>` |
| Everyone | Nothing else: `/`, `/app`, `/desk`, `/login`, `/api/method/login`, other `/api/method/*`, file upload, `/assets`, `/files`, `/private/files`, `/backups`, website pages, the legacy `cmd` RPC |

The token comes from the `ENGINE_INTERNAL_TOKEN` environment variable (32+ characters; the hook also accepts site config key `internal_api_token`, which wins there; set the environment variable in every case because the WSGI layer reads only it). With no valid token configured the internal tier is off (fail closed). Frappe's own authentication and permissions still apply: the token only lets the request reach them. The token is compared in constant time and never logged. The record API is allowed per doctype by Frappe permissions, not by this list; narrow it when the Tool API (OPR-003) fixes the adapter's real HTTP surface.

## Boundary with PLT-024 (gateway)
This work does not rewrite paths, strip headers, rename cookies or map errors. Requests for the gateway (PLT-024):
- Add `X-Internal-Token` on every engine call and strip any client-supplied copy of it.
- Never route customer paths straight to the engine; expose our own API paths only.
- Keep stripping engine-identifying response headers and cookies (the guard's 404 has none, allowed responses do).

## Verification
- Unit: `PYTHONPATH=. python3 -m unittest change_engine.tests.test_erp_020_route_guard change_engine.tests.test_erp_020_wsgi_guard` (in `apps/engine/change_engine`).
- Compose contract: `python3 -m unittest tests.test_erp_020_headless_compose` (run from `infra/dev/docker`; needs Docker for `compose config` only).
- Live: `python3 infra/dev/docker/smoke_headless_engine.py` starts the project `erp020-headless-smoke` (no host ports), creates a synthetic site with the change engine app, checks from a sidecar container on the internal network, and removes only that project.

## Not covered
- Staging crawl for engine markers (ADR-0016 enforcement item) is a separate plan row.
- No TLS, rate limiting or WAF here; those belong to the gateway and hosting rows.
