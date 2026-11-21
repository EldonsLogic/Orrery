# Session log: sec-004-live-bench-attacks

Date: 2026-11-18
Author: partner
Tool and model: claude-code / opus-5.5
Plan IDs: SEC-004

## Summary
Added a live attack suite to PR #131 (SEC-004) that provisions tenant sites A and B, plus a prefix-twin site, with the ERP-003 script on a throwaway bench that has a real worker. It attacks B from A's strongest principals across 22 tests. Result on the live bench: 20 pass and 2 confirmed leaks are recorded as `expectedFailure`.

## Files touched
- `apps/engine/change_engine/change_engine/tests/test_sec_004_live_bench_attacks.py`: live suite. It is skipped unless `SEC004_CONTEXT` is set and fails closed if the context is unusable. Every attack has a positive control so no test can pass vacuously.
- `apps/engine/change_engine/change_engine/tests/sec004_isolation_probe.py`: engine-side helpers called only via `bench execute`. Nothing in it is whitelisted.
- `infra/dev/docker/isolation/{docker-compose.isolation.yml,run_isolation_suite.py,README.md}`: harness. It adds a worker (the base bench has none), refuses any project name without `sec004`, uses port 18404 and tears down with `down -v` only for its own project.
- `docs/log/`: this file.

## Attacks covered (all with A's Administrator session, API token or DB user)
- A's session cookie and API token against B's host.
- Host, X-Forwarded-Host, Forwarded, X-Frappe-Site-Name and similar header swaps.
- B's site name in the path, query, JSON body and `cmd` form.
- B's private and public file URLs, `%2e%2e` and encoded traversal into B's store, and a File record pointing into B's store.
- A's DB user against B's database: no global grants, no other users' processes visible, A's password does not open B's user.
- Redis cache key prefixes, and shared (unprefixed) keys carrying no B data.
- A job enqueued by A that smuggles `site=B` and `user=` kwargs runs as A only.
- B's jobs hidden from A's RQ Job API (list and fetch by id).
- Backups are per site, contain only their own data, and B's backup cannot be downloaded with A's session (direct or by traversal).

## Leaks found (xfail, not fixed here; SECURITY notes in PR #131)
1. HIGH once custom domains exist: the engine's RQ Job list filters with `job_id.startswith(site)`, with no `::` separator. Site `X` therefore lists the jobs of site `X.sa`, including full `arguments` (kwargs) and `exc_info`. Confirmed live: A listed 2 twin jobs whose arguments carried the twin marker.
2. MEDIUM (defence in depth): redis-cache and redis-queue accept unauthenticated clients. Isolation inside Redis is only the `<db_name>|` key prefix, so any code on the engine network can read every tenant's cache and push RQ jobs for any site.
- Related finding, not cross-tenant: the RQ Job list returns HTTP 500 with a full Python traceback (`exc`) unless `order_by` is passed. Tracebacks reaching clients break ADR-0016; the gateway must map them (PLT-024).

## Moves to the gateway and identity layers (once built)
- PLT-024: strip Host, X-Forwarded-*, Forwarded and X-Frappe-Site-Name, and derive the site from the authenticated tenant. Block or map `/private/files`, `/files`, `/backups`, RQ Job routes and engine tracebacks.
- PLT-005: engine `sid` cookies and API keys never reach clients. Tenant-bound sessions and run tokens (ALP-003, ALP-004). These engine-level tests stay as defence in depth.

## Not done or not verified
- The runner's full fresh path (`up`, provision, test, `down -v`) was not run end to end in one go. Its steps were run by hand with the same commands on stack `sec004-isolation`, and `--reuse` mode was run through the runner (exit 0). Full provisioning takes about 15 minutes.
- No CI job runs the live suite. `.github/workflows/` is shared and not in my allowed paths. Request: a nightly or manual job that runs `run_isolation_suite.py` on a Docker runner.
- No infra plan row exists for Redis auth. Request: a row for requirepass or ACL on both Redis services plus a network policy.
- ALP-003 run tokens and ALP-014 grants are not built (PLT-005, OPR-004). The API-token test is the closest engine-level proxy.
- Only the Administrator principal was tested. Low-role users would be strictly weaker.

## Decisions
- My live suite is named `test_sec_004_live_bench_attacks.py` so it does not overwrite PR #131's unit-test file of the same SEC-004 name.

## Tokens or cost
Unknown.

## Next step
Add the CI job above. Add an infra row for Redis auth. Report the RQ Job prefix filter upstream and add a site-naming rule that no site name may be a prefix of another (PLT-003). PLT-024 should take over the header, path and traceback assertions.
