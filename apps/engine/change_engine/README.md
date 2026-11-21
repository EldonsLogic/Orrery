# change_engine

Status: draft | Owner: partner (module author), reviewed by eldon

Frappe app that applies approved configuration changes to an engine site safely. It is the engine-side half of the Blueprint apply path (Part 2) and enforces runtime policies on documents (Part 3). See [docs/architecture/change-engine.md](../../../docs/architecture/change-engine.md) and [engine-adapter.md](../../../docs/architecture/engine-adapter.md).

## What lives here
| Folder | Purpose |
|---|---|
| `change_engine/guarded_apply/` | Deterministic apply layer: safety guardrails (protected ledger/security doctypes and fields), DDL plan gate, six-stage audited deploy with advisory locking, property-setter, workflow and report engines, soft-quarantine rollback, runtime and cross-document policies, compact schema extractor |
| `change_engine/api/endpoints.py` | Whitelisted endpoints (apply, revert, validate proposal, policy read) and document lifecycle hooks |
| `change_engine/api/route_guard.py` | ERP-020 headless guard: `before_request` allowlist that returns a plain 404 for Desk, login, website and every unlisted API route (ADR-0016); see [infra/dev/docker/HEADLESS.md](../../../infra/dev/docker/HEADLESS.md) |
| `change_engine/wsgi.py` | ERP-020: `change_engine.wsgi:application`, the same allowlist applied before the engine sees a request (needed for `/api/method/login`) |
| `change_engine/hooks.py` | Frappe registration: policy enforcement hooks and the route guard |
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
Needs Python 3.10+ and `pydantic>=2`. The full zero-mock Frappe bench integration suite (`test_ce_sec_005_real_bench.py`) runs inside the pinned Docker bench via `python3 infra/dev/docker/run_real_bench_ci.py` (`.github/workflows/real-bench.yml`).

Live MariaDB Suite B requires `pymysql` and a throwaway MariaDB dev stack. It creates the `ce_poc_db` database and recreates tables inside it. Export `DB_USER` and `DB_PASS` with credentials for that stack, and set `DB_HOST` and `DB_PORT` if its address differs from `127.0.0.1:3306`. Run from this directory:

```bash
CE_LIVE_MARIADB_SUITE_B=1 DB_USER="${DB_USER:?Set DB_USER}" DB_PASS="${DB_PASS:?Set DB_PASS}" \
  PYTHONPATH=. python3 -m unittest change_engine.tests.test_live_mariadb_suite_b
```

## Business record outbox (ERP-009)

The allowlist in `change_engine/adapter/record_events.py` covers G1 trading records from [ERP-005](../../../docs/specs/core-module-scope-trading.md), including `on_trash` (`<entity>.deleted`) and `after_rename` (`<entity>.updated`). `hooks.py` registers string hook paths without importing adapter modules at startup. The parent record represents child changes saved through its document lifecycle. Setup metadata, derived ledger rows and direct database writes have separate paths. Each tracked record receives a persistent, reversible surrogate ID (`rec_<ulid>` in `tabChange Engine Event Subject`, preserved across renames and queryable via `resolve_subject_id`) so `subject.id` and `data.id` carry stable references without exposing engine names or PII. An amendment is a new `created` event with `data.amended_from_id` linking to the previous surrogate ID; updates include safe `changed_fields` names. The event ID is also the correlation ID until gateway context is available.

Capture uses the active site's `tenant_id` and DB transaction, and skips cleanly during `in_install`/`in_migrate`/`in_patch` before `erp_009_create_event_outbox` creates the tables (failing closed outside migrations if tables are missing). The scheduler drains committed rows in batches (up to `max_rows=10000` per tick) guarded by an advisory DB lock, and quarantines poison rows (`dead_lettered_at` on corrupt payloads, or when the sink rejects the event itself with an `EventError` `max_attempts=5` times) with a warning log so valid rows behind them continue draining. Any other sink failure is treated as an outage: the row stays pending and retries, so an outage never drops events. If `record_event_sink` is unset while pending rows exist, `publish_pending` logs a warning with the pending count, and `outbox_metrics()` reports current `pending` and `dead_lettered` counts for operator monitoring. A record deleted and later re-created under the same name gets a new surrogate ID; the old ID still resolves to the name. The receiver assigns the tenant-wide stream sequence and de-duplicates by ULID; `publish_pending` deletes a row only after durable acknowledgment.

For a tenant bench, `record_events` constructs and validates Contract 4 envelopes and ULIDs with the Python standard library only (no runtime dependency on `evstream` or `jsonschema` inside the engine container). Ensure `tenant_id` conforms to Contract 4 in trusted site configuration and run `bench --site "$SITE" migrate` before serving record writes. Set `record_event_sink` in trusted site configuration to an installed app's callable implementing BPL-011 `EventStore.append`. Pending rows remain in the site DB while the sink is unconfigured or unavailable. See the [BPL-011 reference](../../../services/blueprint/events/README.md) and [open questions](../../../docs/open-questions.md) (`Q-308`–`Q-312`).

Run the contract and outbox tests from the repository root:

```sh
python3 -m pytest apps/engine/change_engine/change_engine/tests/test_erp_009_record_events.py -q
```

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
