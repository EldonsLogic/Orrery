# change_engine

Status: draft | Owner: partner (module author), reviewed by eldon

Frappe app that applies approved configuration changes to an engine site safely. It is the engine-side half of the Blueprint apply path (Part 2) and enforces runtime policies on documents (Part 3). See [docs/architecture/change-engine.md](../../../docs/architecture/change-engine.md) and [engine-adapter.md](../../../docs/architecture/engine-adapter.md).

## What lives here
| Folder | Purpose |
|---|---|
| `change_engine/guarded_apply/` | Deterministic apply layer: safety guardrails (protected ledger/security doctypes and fields), DDL plan gate, six-stage audited deploy with advisory locking, property-setter, workflow and report engines, soft-quarantine rollback, runtime and cross-document policies, compact schema extractor |
| `change_engine/api/endpoints.py` | Whitelisted endpoints (apply, revert, validate proposal, policy read) and document lifecycle hooks |
| `change_engine/hooks.py` | Frappe registration: policy enforcement hooks only |
| `change_engine/tests/` | Unit tests (standalone, mocked) and one live MariaDB test (needs the dev stack in `infra/dev/docker`) |

## Rules for this module
- No LLM or model-provider code here. Natural-language planning is done by AI services behind the gateway and arrives as a structured Blueprint diff.
- No UI, branding or Desk assets here. The product UI is a separate service.
- Identity and roles come only from the authenticated session. Never accept roles from a request.
- Rigid zone: guardrails on ledger, tax and audit doctypes must not be weakened; any change needs an ADR and security review.
- No client-specific code. Anything customer-specific is configuration compiled from a Blueprint.

## Run the unit tests
```bash
cd apps/engine/change_engine
for t in test_ai_control_plane test_api_deployment test_phase2_property_setter test_phase3_workflow test_phase4_report test_policy_enforcer test_caller_roles; do
  PYTHONPATH=. python3 -m unittest change_engine.tests.$t
done
```
Needs Python 3.10+ and `pydantic>=2`. The live test (`test_live_mariadb_suite_b.py`) needs `pymysql` and the dev stack, and the full zero-mock Frappe bench integration suite (`test_ce_sec_005_real_bench.py`) runs inside the pinned Docker bench via `python3 infra/dev/docker/run_real_bench_ci.py` (`.github/workflows/real-bench.yml`).

## BPL-027 integration test (needs a bench)
`change_engine/tests/test_bpl_027_fixture_real_adapter.py` compiles the trading fixture with the BPL-004 compiler, plans, previews, checks the DDL plan gate, applies it through `ChangeEngineAdapter` + `FrappeRuntimeBackend` on a real site, reads the site back against the Blueprint, re-applies (must be a no-op) and rolls back an incremental change (BPL-008). Without a bench the bench class skips with the reason; two offline tests always run. Use a fresh, disposable site: the test provisions it and leaves configuration behind.

From the repository root, on your own Compose project and port (synthetic data only, credentials from a local secret store, never the repo):
```bash
export COMPOSE_PROJECT_NAME=bpl027-fixture SITE_NAME=bpl027.localhost ENGINE_PORT=18227
read -rsp 'DB root password: ' DB_ROOT_PASSWORD; echo; read -rsp 'Admin password: ' ADMIN_PASSWORD; echo
export DB_ROOT_PASSWORD ADMIN_PASSWORD
DC="docker compose --env-file /dev/null -f infra/dev/docker/docker-compose.dev.yml -f infra/dev/docker/docker-compose.bpl027-test.yml"
$DC up -d --build
$DC exec -T engine sh -ec 'bench new-site "$SITE_NAME" --db-host "$DB_HOST" --mariadb-user-host-login-scope=% --db-root-password "$DB_ROOT_PASSWORD" --admin-password "$ADMIN_PASSWORD" --install-app erpnext --install-app hrms --install-app change_engine'
$DC exec -T engine pip install -q jsonschema==4.26.0   # compiler dependency, test-only, not in the image
$DC exec -T -e BPL027_BENCH_SITE="$SITE_NAME" engine sh -ec 'cd sites && ../env/bin/python -m unittest -v change_engine.tests.test_bpl_027_fixture_real_adapter'
```
The override `docker-compose.bpl027-test.yml` mounts `services/blueprint` and `contracts` read-only and sets `PLATFORM_REPO_ROOT`. To re-run, drop and recreate the site (`bench drop-site "$SITE_NAME" --db-root-password ... --no-backup`). Tear down only your project: `$DC down -v`.

## Known issues
See the status table in [docs/architecture/change-engine.md](../../../docs/architecture/change-engine.md). Licence for this module is TBD (see [docs/legal/checklist.md](../../../docs/legal/checklist.md)).

## Origin
See [PROVENANCE.md](PROVENANCE.md).
