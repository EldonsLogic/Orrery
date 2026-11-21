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
# plus DB_ROOT_PASSWORD, ADMIN_PASSWORD and REDIS_PASSWORD (INF-015) as in README.md
docker compose --env-file /dev/null -f infra/dev/docker/docker-compose.headless.yml up -d --build
```
- No service publishes a host port. The engine listens on 8000 inside the project only.
- Three networks are `internal: true` (no route to the host or the internet): `data` (database and engine), `redis_internal` (the two password-protected Redis services and engine services only, INF-015) and `engine_internal` (engine and its callers). The database and Redis are not on `engine_internal`.
- The `headless` image target preinstalls the app build backend by wheel hash. Startup installs the mounted app with `--no-index --no-build-isolation`; no outbound network is attached. The ordinary developer target is unchanged.
- The gateway is the only ingress. It runs in its own Compose project or file, joins the external network `<project>_engine_internal` and reaches the engine at `engine:8000`, sending the site name in the `Host` header. Only the gateway publishes a port to the outside.
- Anything hosted (shared dev server, staging, production) must use this shape. `docker-compose.dev.yml` alone still publishes the engine on IPv4 loopback for local verification (`verify_dev_bench.py`, phase 0 proofs); that is a developer convenience, not a deployment shape. Open for the founders: drop the loopback port from the dev default once ERP-002 and the proofs no longer need it.
- Do not run the realtime (socket.io) service on a public port either; it is not part of the bench today.

## Layer 2: engine route guard (defence in depth)
The allowlist lives in `apps/engine/change_engine/change_engine/api/route_guard.py` and is applied twice:
- `change_engine/wsgi.py` (`gunicorn change_engine.wsgi:application`, set by the headless compose file): runs before the engine sees the request. This is required, not optional. The smoke test showed that the engine's login manager handles `/api/method/login` while it builds the request, before any `before_request` hook, so the hook alone still lets a login attempt run and answers 401 with engine markers. The default dev entrypoint (`frappe.app:application`) has that gap; hosted environments must use the WSGI entry. The WSGI layer uses the environment tokens only. Before engine initialization it validates bounded JSON/form bodies, restores their bytes, rejects `cmd` and `run_method` in query or body, and rejects bodies on GET. The anonymous probe accepts no credentials, query or body; its response is rebuilt without engine cookies or error pages.
- A `before_request` hook in `hooks.py`: second layer, checks the parsed query/form arguments and the same environment tokens. Site-config token overrides are not used. Both layers reject site-selection headers; the gateway selects the tenant with Host. It denies every request unless it matches the allowlist, with a plain 404 that carries no engine marker and no cookie.

| Caller | Allowed |
|---|---|
| Anyone | `GET /api/method/ping` (liveness) |
| Holder of the internal token (header `X-Internal-Token`) | `POST /api/method/change_engine.api.endpoints.<adapter method>` (twelve whitelisted methods) and read-only `GET /api/resource/<DocType>[/<name>]` for Customer, Item, Sales Order and Sales Invoice. Writes use guarded adapter endpoints; all other DocTypes are denied |
| Everyone | Nothing else: `/`, `/app`, `/desk`, `/login`, `/api/method/login`, other `/api/method/*`, file upload, `/assets`, `/files`, `/private/files`, `/backups`, website pages, the legacy `cmd` RPC |

The environment token is an interim G1 internal service credential, not the final SEC-002 workload identity or a tenant identity. It admits requests to the engine's own user permission checks. `ENGINE_INTERNAL_TOKEN` must contain 32–256 URL-safe characters; generate it from secure random bytes, not a memorable string. The startup validator refuses malformed or absent current credentials before opening the listener. Missing/invalid credentials also fail closed in each request guard. No credential values are logged.

For rotation, distribute the new current token to callers while setting `ENGINE_INTERNAL_TOKEN_PREVIOUS` to the old token, then remove the previous value once callers have migrated. The previous token never works without a valid current token; a configured malformed previous token prevents startup. Site-config overrides are intentionally unsupported so both layers use identical credentials. The overlap ends operationally when the previous variable is removed; no timed secret-store rotation is claimed.

## Boundary with PLT-024 (gateway)
This work does not rewrite paths, strip headers, rename cookies or map errors. Requests for the gateway (PLT-024):
- Add `X-Internal-Token` on every engine call and strip any client-supplied copy of it.
- Never route customer paths straight to the engine; expose our own API paths only.
- Keep stripping engine-identifying response headers and cookies (the guard's 404 has none, allowed responses do).

## Verification
- Unit: `PYTHONPATH=. python3 -m unittest change_engine.tests.test_erp_020_route_guard change_engine.tests.test_erp_020_wsgi_guard` (in `apps/engine/change_engine`).
- Compose contract: `python3 -m unittest tests.test_erp_020_headless_compose` (run from `infra/dev/docker`; needs Docker for `compose config` only).
- Live: `python3 infra/dev/docker/smoke_headless_engine.py` starts a unique project prefixed `erp020-headless-smoke-` (no host ports), creates a synthetic site with ERPNext and the change engine app, checks from a sidecar container on the internal network, and removes only that project.

## Not covered
- Engine-side ingress protection only: full ADR-0016 invisibility for allowed business responses still requires PLT-024 and the QA-016 staging crawl. Those are not claimed here.
- No TLS, rate limiting or WAF here; those belong to the gateway and hosting rows.
