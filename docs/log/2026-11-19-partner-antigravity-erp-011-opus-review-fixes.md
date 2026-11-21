# Session log: erp-011-opus-review-fixes

Date: 2026-11-19
Author: partner
Tool and model: antigravity
Plan IDs: ERP-011,ERP-028

## Summary
Addressed all MED and LOW findings from Eldon's cross-model Opus review on PR #192 (`ERP-011`): enforced credit-authorising session roles on `set_credit_limit`, capped volume discounts below 100%, mapped invalid rep master commission rates to `TRD-REP`, marked `strings.json` entries `unreviewed` (ADR-0033) and fixed `TRD-CONTEXT` Arabic, wired ERP-011 unit and factory sandbox checks into `.github/workflows/tests.yml`, updated `ERP-028` plan scope for keyed upserts and journal/recovery tests (ADR-0028), and verified 6 live rollback-only proofs with zero DB leftovers on Frappe 15.126.0 / ERPNext 15.124.5.

## Files touched
- `components/sales/trading/trading.py`: added `_CREDIT_ROLES` / `_require_credit_role()` check (`TRD-ROLE`) in `set_credit_limit`, rejected `discount >= 100` in `create_volume_discount`, and mapped invalid `Sales Person.commission_rate` to `TRD-REP` in `set_sales_team`.
- `components/sales/trading/strings.json`: added `"review": "unreviewed"` on all keys per ADR-0033, added `TRD-ROLE`, fixed `TRD-CONTEXT` Arabic (`ومستأجر`), and clarified `TRD-REP`.
- `components/sales/trading/tests/test_trading.py`: added 14 boundary tests covering credit-role denial/allow, 100% discount rejection, invalid master commission rates raising `TRD-REP`, and `strings.json` review metadata (78 tests total, all passing).
- `components/sales/trading/tests/bench_trading.py`: added 6th live proof verifying a stock `Sales User` (with native `Customer` write permission) is denied `set_credit_limit` with `TRD-ROLE` and leaves the limit unchanged.
- `components/sales/trading/README.md`: documented ADR-0027 credit-role gate, CI workflow wiring, 6-proof live bench verification (including zero-leak savepoint rollback), and ADR-0028 `ERP-028` requirements.
- `.github/workflows/tests.yml`: added `Trading and distribution pack unit and factory sandbox checks (ERP-011)` step running pytest and `factory check --run-tests --trusted-source`.
- `docs/PLAN.md`: updated `ERP-028` row to require keyed upserts for `create_*` plus journal and recovery tests (ADR-0028).

## Decisions
- `set_credit_limit` requires an active session role in `{'Credit Controller', 'Accounts Manager', 'System Manager'}` via `engine.get_roles()` because stock ERPNext grants `Sales User` `permlevel=0` write access on `Customer` and `Customer Credit Limit` (verified against live doctype JSONs). Full approval workflow binding remains `ERP-008` / `ERP-023` / `ERP-028`.

## Verification
- TDD red confirmed 11 new/tightened tests failing before edits; TDD green: `78 passed` in `components/sales/trading/tests`.
- `factory check components/sales/trading --run-tests --trusted-source`: `ok: true`, `findings: []`, `analysis.issues: []`, `78 passed`.
- `services/blueprint/tests/registry` and `services/blueprint/tests/factory`: `196 passed`.
- Live rollback-only `bench_trading.py:run(frappe)` on `platform-erp001-20261111b-engine-1` (`erp001.localhost`, Frappe 15.126.0 / ERPNext 15.124.5): all 6 proofs passed; post-run DB existence check on all 8 synthetic fixtures returned `LEFTOVERS: []`.

## Tokens or cost
Unknown.

## Next step
Await Eldon's human line-by-line review on Tier 3 PR #192 (`ERP-011`, ADR-0031); hold `ERP-028` until PR #192 merges.
