# Session log: bpl-008-blueprint-rollback

Date: 2026-11-18
Author: partner
Tool and model: antigravity
Plan IDs: BPL-008

## Summary
Completed `BPL-008` Blueprint rollback end-to-end across the Frappe runtime backend, adapter state hydration, and simulated runtime, with byte-identical export restoration, soft-quarantine of required fields (`hidden=1`, `reqd=0`), Property Setter deletion on unset, and persisted state recovery across adapter restarts.

## Files touched
- `apps/engine/change_engine/change_engine/adapter/storage.py`: Added `SQLiteAdapterStore.hydrate_site` to restore persisted `SiteRecord` instances into adapter storage.
- `apps/engine/change_engine/change_engine/adapter/frappe_backend.py`: Added `load_site_state` for restarted-adapter recovery, `/options` property mapping, Property Setter deletion on unset (`_delete_property_setter`), `reqd=0` + `hidden=1` soft-quarantine with DocType cache invalidation (`_quarantine_field`), country-pack default restoration on `settings.set` unset, and cache clearing on `workflow.disable` / `report.disable`.
- `apps/engine/change_engine/change_engine/adapter/engine.py`: Added `ChangeEngineAdapter._get_or_hydrate_site` across RPC dispatch and test probes, plus empty sub-dict pruning on `.set_property`/`.configure` unset for byte-identical rollback exports.
- `apps/engine/change_engine/change_engine/adapter/simulated_frappe.py`: Checked `DELETE FROM \`tabProperty Setter\`` before `SELECT ... FROM \`tabProperty Setter\`` in `SimulatedFrappeDB.sql` so Property Setter deletions execute cleanly.
- `apps/engine/change_engine/change_engine/tests/test_bpl_008_blueprint_rollback.py`: Added 6 end-to-end rollback verification tests covering multi-version chains, workflow child-table rollback, restarted-adapter hydration, rollback compensation / `recovery_required`, direct RPC rollbacks, and real `services/blueprint` compiler + `bpdiff` integration.
- `.github/workflows/tests.yml`: Added `test_bpl_008_blueprint_rollback.py` to `python-tests`.
- `docs/PLAN.md`: Marked `BPL-008` as `done`.

## Decisions
- None.

## Tokens or cost
Unknown.

## Next step
Pick up `ERP-002` (Spike: 50-tenant load test on one bench pool), then `SEC-004` and `CE-SEC-005`.
