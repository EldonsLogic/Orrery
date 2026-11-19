# change_engine

Status: draft | Owner: partner (module author), reviewed by eldon

Frappe app that applies approved configuration changes to an engine site safely. It is the engine-side half of the Blueprint apply path (Part 2) and enforces runtime policies on documents (Part 3). See [docs/architecture/change-engine.md](../../../docs/architecture/change-engine.md) and [engine-adapter.md](../../../docs/architecture/engine-adapter.md).

## What lives here
| Folder | Purpose |
|---|---|
| `change_engine/guarded_apply/` | Deterministic apply layer: safety guardrails (protected ledger/security doctypes and fields), DDL plan gate, six-stage audited deploy with advisory locking, property-setter, workflow and report engines, soft-quarantine rollback, runtime and cross-document policies, compact schema extractor |
| `change_engine/api/endpoints.py` | Whitelisted endpoints (apply, revert, validate proposal, policy read) and document lifecycle hooks |
| `change_engine/hooks.py` | Frappe registration for policy enforcement, record lifecycle capture and the outbox relay |
| `change_engine/adapter/record_events.py` | Transactional tenant outbox and Contract 4 publisher (ERP-009) |
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
Needs Python 3.10+ and `pydantic>=2`. The live test (`test_live_mariadb_suite_b.py`) needs `pymysql` and the dev stack. None of this has run inside a real Frappe bench yet (CE-SEC-005).

## Business record outbox (ERP-009)

The allowlist in `change_engine/adapter/record_events.py` covers G1 trading records from [ERP-005](../../../docs/specs/core-module-scope-trading.md), including `on_trash` (`<entity>.deleted`) and `after_rename` (`<entity>.updated`). `hooks.py` registers string hook paths without importing adapter modules at startup. The parent record represents child changes saved through its document lifecycle. Setup metadata, derived ledger rows and direct database writes have separate paths. Each tracked record receives a persistent, reversible surrogate ID (`rec_<ulid>` in `tabChange Engine Event Subject`, preserved across renames and queryable via `resolve_subject_id`) so `subject.id` and `data.id` carry stable references without exposing engine names or PII. An amendment is a new `created` event with `data.amended_from_id` linking to the previous surrogate ID; updates include safe `changed_fields` names. The event ID is also the correlation ID until gateway context is available.

Capture uses the active site's `tenant_id` and DB transaction, and skips cleanly during `in_install`/`in_migrate`/`in_patch` before `erp_009_create_event_outbox` creates the tables (failing closed outside migrations if tables are missing). The scheduler drains committed rows in batches (up to `max_rows=10000` per tick) guarded by an advisory DB lock, and quarantines poison rows (`dead_lettered_at` on corrupt payloads, or when the sink rejects the event itself with an `EventError` `max_attempts=5` times) so valid rows behind them continue draining. Any other sink failure is treated as an outage: the row stays pending and retries, so an outage never drops events. A record deleted and later re-created under the same name gets a new surrogate ID; the old ID still resolves to the name. The receiver assigns the tenant-wide stream sequence and de-duplicates by ULID; `publish_pending` deletes a row only after durable acknowledgment.

For a tenant bench, `record_events` imports `evstream` directly, from `ORRERY_EVSTREAM_DIR`, or by discovering `services/blueprint/events` in the repository tree (no manual `PYTHONPATH` needed in-repo). Install the app's dependencies, including `jsonschema`, ensure `tenant_id` conforms to Contract 4, and run `bench --site "$SITE" migrate` before serving record writes. Set `record_event_sink` in trusted site configuration to an installed app's callable implementing BPL-011 `EventStore.append`. Pending rows remain in the site DB while the sink is unconfigured or unavailable. See the [BPL-011 reference](../../../services/blueprint/events/README.md) and [open questions](../../../docs/open-questions.md) (`Q-217`–`Q-221`).

Run the contract and outbox tests from the repository root:

```sh
python3 -m pytest apps/engine/change_engine/change_engine/tests/test_erp_009_record_events.py -q
```

## Known issues
See the status table in [docs/architecture/change-engine.md](../../../docs/architecture/change-engine.md). Licence for this module is TBD (see [docs/legal/checklist.md](../../../docs/legal/checklist.md)).

## Origin
See [PROVENANCE.md](PROVENANCE.md).
