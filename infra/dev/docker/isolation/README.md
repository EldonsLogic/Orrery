# Cross-tenant isolation harness (SEC-004)

Status: development
Owner: partner
Plan ID: SEC-004

Throwaway bench for the cross-tenant isolation suite
([test_sec_004_live_bench_attacks.py](../../../../apps/engine/change_engine/change_engine/tests/test_sec_004_live_bench_attacks.py)).
Synthetic data only. Not for shared or hosted environments.

## Run
From the repository root, on a `linux/amd64` machine with Docker Compose v2:
```bash
python3 infra/dev/docker/isolation/run_isolation_suite.py            # up, provision, test, down -v
python3 infra/dev/docker/isolation/run_isolation_suite.py --keep     # leave the stack up
python3 infra/dev/docker/isolation/run_isolation_suite.py --reuse <context.json>  # re-run tests only
```
Defaults: Compose project `sec004-isolation` (the name must contain `sec004`; the runner refuses anything else, so it never touches the dev, ERP-001 or ERP-002 stacks) and engine port `127.0.0.1:18404`. Teardown runs `docker compose down -v` for that project only.

## What it sets up
- The ERP-001 dev bench plus a background `worker` service ([docker-compose.isolation.yml](docker-compose.isolation.yml)); the base bench runs none, and job-context isolation needs a real worker.
- Three sites created with the ERP-003 script ([provision_tenant.sh](../provision_tenant.sh)), each with its own random admin and database passwords in 0600 files under a private temp directory:
  - A `sec004-tenant-a.localhost` (SA) and B `sec004-tenant-b.localhost` (AE) with the default app set;
  - a prefix twin `sec004-tenant-a.localhost.sa` (change_engine only), the `acme.com` vs `acme.com.sa` case, to catch prefix-matching site filters.

Full provisioning takes tens of minutes (two full ERPNext + HRMS installs). The suite itself takes a few minutes.

## Reading the result
`expected failure` lines are known leaks, documented in each test's docstring and in the SEC-004 PR. An `unexpected success` means a leak is gone: remove the `expectedFailure` marker. Any plain failure is a new isolation regression.
