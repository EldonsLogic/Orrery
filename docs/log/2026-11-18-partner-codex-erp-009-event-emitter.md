# Session log: erp-009-event-emitter

Date: 2026-11-18
Author: partner
Tool and model: codex / gpt-6.2-sol
Plan IDs: ERP-009

## Summary
Registered G1 trading document lifecycle hooks and added a per-site transactional outbox that relays committed record events through the BPL-011 append interface.

## Files touched
- `apps/engine/change_engine/change_engine/adapter/record_events.py` and `hooks.py` (app package): capture and publish lifecycle events, using the existing adapter's entity mapping and bounded lock key.
- `apps/engine/change_engine/change_engine/patches/erp_009_create_event_outbox.py` and `patches.txt` (app package): install and migrate the outbox table.
- `apps/engine/change_engine/change_engine/tests/test_erp_009_record_events.py`: schema, event order, lifecycle, rollback, retry, tenant scoping, invalid acknowledgement and engine disclosure checks.
- `apps/engine/change_engine/README.md` and `pyproject.toml`: deployment instructions and shared schema validation dependency.
- `docs/PLAN.md`: claimed ERP-009 for the partner and left it `doing` for review.
- `docs/open-questions.md`: Q-150 to Q-154.

## Decisions
- Use [ADR-0006](../decisions/ADR-0006-tenancy-site-per-tenant.md) for site isolation and [ADR-0016](../decisions/ADR-0016-engine-invisibility.md) for the event envelope. The scheduler drains committed rows per site. The receiver assigns the stream sequence and de-duplicates on the stored ULID.
- Amendments use `created` with `data.amended_from_id`. The event carries opaque record and session-actor IDs and uses the event ID as its correlation ID until gateway context is defined. The capture covers the G1 trading allowlist and the registered document hooks.
- This is founder-directed G1 preparation while G0 remains current. The event receiver, gateway context, tenant ID format and any broader scope are open. The local integration used the BPL-011 reference store with synthetic data. A deployed durable receiver is still required.

## Verification
- `PYTHONPATH=apps/engine/change_engine:services/blueprint/events:. python3 -m pytest apps/engine/change_engine/change_engine/tests -q -rs` with an isolated MariaDB 11.4 and WeasyPrint: 194 passed, including 13 ERP-009 cases, with 54 subtests passing. WeasyPrint emitted an existing backend deprecation warning.
- Fresh synthetic bench on MariaDB 11.4: app install created the table and scheduler registration. Real `Contact` insert/update committed and published in order, while rollback removed both the document and its outbox row.
- `python3 -m pytest services/blueprint/tests/events -q`: 87 passed.
- `PYTHONPATH=services/blueprint:apps/engine/change_engine ADAPTER_HARNESS=change_engine.adapter.harness:make_harness python3 -m pytest services/blueprint/tests/adapter -q`: 208 passed. Repeated with `ADAPTER_HARNESS=change_engine.adapter.harness:make_frappe_harness`: 208 passed.

## Tokens or cost
Unknown.

## Next step
Cross-model review of ERP-009. Confirm the event receiver and identity/correlation handoff before enabling production publication.
