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
Needs Python 3.10+ and `pydantic>=2`. The live test (`test_live_mariadb_suite_b.py`) needs `pymysql` and the dev stack. None of this has run inside a real Frappe bench yet (CE-SEC-005).

## Known issues
See the status table in [docs/architecture/change-engine.md](../../../docs/architecture/change-engine.md). Licence for this module is TBD (see [docs/legal/checklist.md](../../../docs/legal/checklist.md)).

## Origin
See [PROVENANCE.md](PROVENANCE.md).
