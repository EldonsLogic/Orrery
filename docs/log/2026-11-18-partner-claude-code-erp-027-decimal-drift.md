# Session log: erp-027-decimal-drift

Date: 2026-11-18
Author: partner
Tool and model: claude-code / sonnet-5.5
Plan IDs: ERP-027

## Summary
Reproduced the Phase 0 false `MODIFY COLUMN` drift against the live bench, found that BPL-007 had already suppressed the zero-default phantom on the Frappe path, and hardened the gate and added regression tests for the four core DocTypes; `ERP-027` is done, with one CI line still to add (below).

## What was found
- Phase 0 finding is `E0-7` #1 in `docs/architecture/phase0-engine-proof-report.md`: MariaDB reports `'0.000000000'` as the default of decimal(21,9) columns that DocFields declare with no default, so Frappe's `default_changed_for_decimal` emits phantom `MODIFY` statements.
- Live bench (`erp001.localhost`, read-only probe, nothing written): raw `MariaDBTable.alter()` emits 651 phantom decimal `MODIFY` clauses across 474 DocTypes; the BPL-007 `_normalize_zero_decimal_defaults` already removes all of them (residual 13, all non-decimal: json/varchar/time/index, none on Customer, Sales Order, Sales Invoice or Item). So the headline defect was already fixed by BPL-007; the live gate approved all 4 DocTypes x 8 fieldtypes before my change.
- What was missing: no test drove the Frappe-native path (only the helper on synthetic dicts), the comparison was fragile to equivalent type spellings (`DECIMAL(21,9)`, `decimal(21, 9)`, bare `decimal`) and to `Rating` zero defaults, and nothing pinned that genuine drift is still rejected.

## Files touched
- `apps/engine/change_engine/change_engine/guarded_apply/ddl_plan_gate.py`: `_canonical_column_type` (case, whitespace, bare `decimal` = `decimal(10,0)`; any other precision/scale, `unsigned` or other type stays different), used by the simulator type compare, new `_canonicalize_current_column_types` called in the Frappe path, and `Rating` added to the decimal fieldtypes whose zero default is normalized.
- `apps/engine/change_engine/change_engine/tests/test_erp_027_decimal_drift.py`: 17 tests (34 subtests): Frappe-path stand-in that copies Frappe v15 comparison logic, a guard that it reproduces the phantom, 4 core DocTypes x 4 fieldtypes approved, type-spelling and default-format variants not drift, and precision, scale, unsigned, different type, non-zero default, differing DocField default, unparseable default all still rejected. With the normalization disabled 29 of the 34 suppression cases fail, so the tests do bite.
- `docs/PLAN.md`: `ERP-027` set `done`.

## Verified
- `PYTHONPATH=apps/engine/change_engine pytest` on test_erp_027 (17 passed), test_bpl_007 (5), test_bpl_012 (8), test_erp_012 (7), test_erp_021 (7): all pass (venv with pytest, pydantic>=2).
- Live bench, my patched gate loaded read-only via `docker cp` to `/tmp` (removed afterwards), no container touched otherwise: 4 DocTypes x 8 fieldtypes approved with a single `ADD COLUMN`; negative controls injecting `decimal(18,6)`, `decimal(21,2)`, `decimal(21,9) unsigned` and a `5.000000000` default into `grand_total` were all rejected.

## NOT done or NOT verified
- CI: the new test file is not wired into `.github/workflows/tests.yml` (outside my allowed paths). Request: add a step `PYTHONPATH=apps/engine/change_engine python3 -m pytest apps/engine/change_engine/change_engine/tests/test_erp_027_decimal_drift.py -q` next to the BPL-007 step.
- The Frappe-path tests use a stand-in that copies Frappe v15 logic (frappe is not installable here); the live bench probe is manual, not in CI. Live DB type-spelling variants could not be produced without altering a shared database, so those are covered by unit tests only.
- Open risk, not changed: `inspect_frappe_ddl_plan` falls back to the pure-Python simulator whenever the Frappe path raises (`_inspect_with_frappe_mariadb_table` returns None on any exception). The simulator knows only standard columns, so on a live bench that fallback cannot see real drift (fails open). Suggest a follow-up row: when frappe is initialised and the table exists, reject instead of falling back.
- Not run: other Frappe versions or MariaDB 11; only `v15.124.5` on MariaDB 10.6 was probed.

## Decisions
- None. No ADR needed (no auth, tenancy, contract or compliance change; the gate stays stricter-or-equal in every rejecting case).

## Tokens or cost
Unknown.

## Next step
Add the CI line above (shared path, other founder's review); decide on the fail-open fallback row; `ERP-002` and Eldon's `BPL-029` mapping correction are unaffected.
