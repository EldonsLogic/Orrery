# Session log: bpl-031-entity-add-existing-doctype

Date: 2026-11-23
Author: partner
Tool and model: claude-code
Plan IDs: BPL-031

## Summary
`entity.add` on an existing engine document type now adds the Blueprint's fields as custom fields through the guarded field path, an entity the mapping contract maps to a built-in type never becomes a custom twin, and bench `test_05` derives its expectations from the contract and no longer carries `expectedFailure`. Offline tests prove it; the bench run is left to CI's real-bench job (no bench here).

## What changed
- `adapter/mapping.py`: `CONTRACT_ENTITY_TO_DOCTYPE` (purchasing mapping 0.2.0: supplier, price list, price list item to Item Price, purchase order, receipt and invoice with their lines) is consulted by `entity_to_doctype`, so `purchase_order_line` is "Purchase Order Item" and no longer "Purchase Order Line". These entities stay out of the SEC-022 grant allowlist (`ENTITY_TO_DOCTYPE`, `reviewed_grant_doctype` untouched); on a real site the existing own-type checks still refuse a grant on a built-in because its DocType row is custom=0. `is_contract_mapped_entity` added.
- `adapter/frappe_backend.py` `_add_entity` (entity.add branch only): contract-mapped and present, add each Blueprint field as a custom field unless the type already holds a field with that custom name or the exact Blueprint id (native same-name field, no twin); contract-mapped and missing, refuse `subject_missing`; unsupported field type, refuse `unsupported_value_type`, all before any write. No mapping: create one adapter-owned custom type (ADR-0051 item 3) once; if the derived name is an engine type the adapter did not make, refuse `protected_subject` (it used to apply nothing and report success).
- `adapter/simulated_frappe.py`: the simulated site now holds the 11 built-ins the contract names that it lacked (Delivery Note, Supplier, Price List, Item Price, purchase documents and their item tables).
- Tests: new `tests/test_bpl_031_entity_add_existing_doctype.py` (11 tests); `test_bpl_027...`: `expected_engine_config` reads both contract examples, new `entity_gaps` (missing types and fields, plus custom types that are not an expected unmapped entity), `test_05` uses it and is no longer `expectedFailure`; `test_06c` expectations updated (see below); `ci_engine_fake.py`: 5 built-in child and price types seeded; `test_bpl_008...` `test_06`: strips grants on unmapped built-ins like the BPL-027 tests do; `.github/workflows/tests.yml`: new file added to the BPL-027 step.
- Test-first: the 8 new tests that cover the fix failed before the change, all pass after.

## Verification
- `PYTHONPATH=apps/engine/change_engine uvx --with pyyaml --with jsonschema --with pydantic pytest -q` on the BPL-027 and BPL-031 files: 20 passed, 11 skipped (bench tests skip without a bench).
- All 51 offline files listed in `tests.yml` (with pymysql and werkzeug added): 1343 passed, 28 failed, all in `test_cmp_005_*`, `test_erp_007_*` and `test_erp_016_*`, caused by `HijriDateError: Calendar conversion is unavailable` (a missing converter library in this environment, not adapter code); `test_bpl_008` failed once from this change and was fixed (passes, 6 of 6). Not re-run on a clean main here, so the 28 are UNVERIFIED as pre-existing; the cause is unrelated.
- `python3 scripts/check_repo_hygiene.py`: OK.

## Decisions and open points (for the founders)
- The mapping contract says nothing about an entity it does not map (quotes, credit notes, payments, stock transfers: 7 custom types on the fixture). ADR-0051 item 3 already allows adapter-owned custom types for them, so that is kept and cited in code; they are not duplicates by name. If the founders want them refused or mapped (Quotation, Payment Entry, Stock Entry), that is a contract change (Eldon's lane).
- Unique and indexed Blueprint fields on a built-in type (`customer_code`, `supplier_code`, `item_code` is native) are added WITHOUT the constraint, with a warning logged. The guarded field path refuses unique and index DDL (it queues it for a controlled admin deployment) and the gate approval is not passed to the backend, so applying them is a DDL-gate design decision (security review), not done here. Open question to add.
- The adapter does not read the mapping file; most mapped fields have a different engine name (`quantity` to `qty`), so those get a custom twin next to the native field. Only a native field of the same name is reused. Consuming `engineField` is the real fix and needs the mapping loaded by the adapter (BPL-029 follow-up).
- Relations in an entity definition are still not applied (as before); `test_05` checks fields only.
- `test_06c` changed on purpose: with Customer and Item now holding `credit_limit` and `cost_price`, the grants that hide them are applied (field levels 2 and 1 and two Property Setters), where the old test asserted they were withheld because the engine did not hold the fields. This code path (BPL-032 hidden fields) has not run on a real bench yet.

## What CI's real bench must prove
`test_05` (types exist under contract names, every field native or custom, no custom twin; 7 expected custom types only); `test_03b` still applies the full mapped fixture (custom field DDL for every supported Blueprint type on real built-ins, including child tables and decimal fields); `test_06` still passes now that hidden fields exist; `test_07` re-apply no-op; `test_08` rollback.

## Files touched
- apps/engine/change_engine/change_engine/adapter/mapping.py, frappe_backend.py, simulated_frappe.py
- apps/engine/change_engine/change_engine/tests/test_bpl_031_entity_add_existing_doctype.py (new), test_bpl_027_fixture_real_adapter.py, test_bpl_008_blueprint_rollback.py, ci_engine_fake.py
- .github/workflows/tests.yml (test path added)

## Tokens or cost
Unknown.

## Next step
Push and open the PR for review by a different model; watch the real-bench job (BPL-031 `test_05`, `test_03b`, `test_06`). Then BPL-027 can close. Follow-ups: gate-approved unique and index DDL for built-in types, adapter reads the mapping (`engineField`), BPL-034 grant allowlist.

## Packaging notes (coordinator, Claude Opus 5.5)
- Branch cut from current main, which now includes #280 and #281 (BPL-032 purchasing grants). `test_bpl_027_fixture_real_adapter.py::test_06c` conflict resolved by keeping main's purchasing-grant assertions and this PR's field-level assertion (`Customer` level 2, `Item` level 1). The `test_bpl_008` grant-stripping change was dropped: after #281 the purchasing types are in the grant table, and main's version passes unchanged.
- Open questions added: Q-603 (unique and index DDL on built-ins), Q-604 (adapter reads `engineField`), Q-605 (unmapped entities in the contract).
- CI-listed engine tests: 1,410 passed; the 27 failures are the Hijri-date suites that fail identically without this change (local library gap).
