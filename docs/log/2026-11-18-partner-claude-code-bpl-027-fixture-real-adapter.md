# Session log: bpl-027-fixture-real-adapter

Date: 2026-11-18
Author: partner
Tool and model: claude-code / opus-5.5
Plan IDs: BPL-027

## Summary
Added an end-to-end integration test that compiles the trading fixture with the BPL-004 compiler and runs plan, preview, the DDL gate, apply, read-back, re-apply and rollback through `ChangeEngineAdapter` + `FrappeRuntimeBackend` on a real, freshly created bench site. Fixed two real adapter defects it exposed. Apply, the no-op re-apply and rollback pass on the real engine. Three Blueprint-conformance gaps remain, recorded as expected failures, so the row stays `doing`.

## Files touched
- `apps/engine/change_engine/change_engine/tests/test_bpl_027_fixture_real_adapter.py`: new. 4 offline tests (always run) and 9 bench tests (skip with an explicit reason unless `BPL027_BENCH_SITE` is set and `frappe` plus the compiler can be imported).
- `apps/engine/change_engine/change_engine/adapter/engine.py`: `_exec` now undoes its in-memory config change when the engine call fails (defect 2).
- `apps/engine/change_engine/change_engine/adapter/frappe_backend.py`: warehouse `location.upsert`/`location.disable` find and create warehouses by `warehouse_name` + company, and fail closed with `site_not_ready` when the engine requires a company and the site has none (defect 1).
- `apps/engine/change_engine/README.md`: section "BPL-027 integration test", with exact run steps.
- `infra/dev/docker/docker-compose.bpl027-test.yml`: test-only Compose override (read-only mounts of `services/blueprint` and `contracts`, sets `PLATFORM_REPO_ROOT`).
- `docs/PLAN.md`: BPL-027 `todo` -> `doing` (partner).

## Defects fixed (each with a test that fails without the fix)
1. A warehouse insert never set `company`, which is mandatory in the engine, so every warehouse `location.upsert` failed on a real site. The lookup used the bare id, but the engine names warehouses `<name> - <abbr>`, so a re-apply would also miss the record. Test: `test_warehouse_lookup_uses_company_and_fails_closed_without_one`.
2. `_exec` changed the adapter's in-memory config before calling the engine. When the engine call failed, the change stayed, the compensation hash check failed, and the site went to `recovery_required` instead of `compensated`. The simulated runtime hid this because injected faults fire before `_exec`. Test: `test_engine_failure_mid_apply_compensates_without_recovery_required`.

## Findings not fixed (need decisions; recorded as `expectedFailure` tests)
1. **Name collisions with built-in records (security).** The engine matches record names without case. Blueprint role `auditor` therefore resolves to the engine's built-in `Auditor` role, with that role's standard permissions. State `approved` becomes the built-in `Approved` workflow state. This breaks the mapping-contract rule that adapter roles are its own, never built-in ones. It needs a namespacing decision for roles and states (it touches access, so it needs a security review). Test: `test_04b`.
2. **Fields and doctypes.** `entity.add` on an existing engine document type adds none of the Blueprint's fields: 61 fields are missing on the fixture, for example `Customer.vat_number` and `Sales Invoice.zatca_uuid`. Entities without a hard-coded mapping become 12 new custom document types that duplicate built-in ones (`Payment`, `Credit Note`, `Sales Quote`, `Stock Transfer`, `* Line`). The adapter does not consume the engine mapping (BPL-029 / `contracts/engine-mapping.md`). Test: `test_05`.
3. **Permissions.** `role.upsert` creates the role only. No Blueprint permission reaches the engine (actions, hidden fields, read-only fields): 160 expected grants are missing. Test: `test_06`.
4. The compiler emits adapter id `change_engine`, but the adapter accepts only `frappe` (compiler open question 4). The test retargets and reseals the artifact.
5. Blueprint type `attachment` is refused by plan (`unsupported_value_type` at `/entities/purchase_invoice`), consistent with the fake. The test asserts this, then swaps the field to `string` for the rest of the run.
6. Report `stock_on_hand` has no entity in the Blueprint. The adapter silently binds it to `Sales Order`.
7. Adapter post-conditions are evaluated against the adapter's own config copy, not the engine. Only this test's read-back checks the engine.
8. ERP-027 (decimal false drift) was not hit: no field.add on Customer, Sales Order, Sales Invoice or Item runs in this flow, because finding 2 skips those fields.

## Verification
- Fresh bench site (own Compose project `bpl027-fixture`, port 18227, synthetic company set up by the test): `../env/bin/python -m unittest -v change_engine.tests.test_bpl_027_fixture_real_adapter` run in the engine container from the bench `sites` directory with `BPL027_BENCH_SITE=bpl027.localhost` -> `Ran 13 tests ... OK (skipped=1, expected failures=3)`. Passed: provision; raw fixture refused; plan `needs_gate_approval` (unique_or_index + protected_subject); preview; apply without `gateApproved` refused with no engine change; apply `applied` with `exportHash == predictedExportHash`; read-back of roles, workflows, reports, warehouses and settings (case-insensitive); re-apply idempotent replay plus restarted adapter `already_applied` with an unchanged engine fingerprint; v2 field add then rollback (field hidden, column kept, exportHash back to v1).
- Offline: `pytest` on BPL-027, BPL-012, ERP-012, BPL-007, BPL-008 and ERP-021 tests -> 37 passed, 9 skipped. BPL-025 conformance (`services/blueprint/tests/adapter`) under `make_harness` and `make_frappe_harness` -> 215 passed each. `infra/dev/docker/tests` -> OK.
- Each defect test was confirmed to fail with the fix reverted.
- Bench torn down (`down -v` on `bpl027-fixture` only). The ERP-002 and ERP-001 containers were not touched.

## Not done or not verified
- Acceptance is not fully met (findings 1-3), so the row stays `doing`.
- The bench test is not in CI (no bench there). The offline tests are also not wired into `.github/workflows/tests.yml`, which is a shared path outside this task. Request: add a step running `test_bpl_027_fixture_real_adapter.py` with `PYTHONPATH=apps/engine/change_engine`.
- `jsonschema` is installed by hand in the bench container; it is not added to the image.
- After the bench run, two default paths (repo root, sites path) changed from absolute container paths to `~`-relative ones expanded at runtime, to pass the repo hygiene check. Behaviour is the same in the container (home is the bench user's), but this form was not re-run on a bench; the offline tests and `docker compose config` were re-checked.
- On a fresh site, Frappe prints a stack trace when the adapter probes its not-yet-created state table. It is caught and harmless, but noisy.

## Decisions
- None. Findings 1-3 need founder decisions and new plan rows: role/state namespacing (security review); a mapping-driven `entity.add` and field apply; role permission apply.

## Tokens or cost
Unknown.

## Next step
Founders: decide plan rows for findings 1-3. When they land, remove the matching `expectedFailure` and set BPL-027 `done`. Wire the offline BPL-027 tests into CI.
