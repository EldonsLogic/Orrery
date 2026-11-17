# Phase 0 Engine Proof Report (`ERP-021`)

Status: draft
Owner: partner
Plan ID: ERP-021

Empirical validation of the pinned Frappe/ERPNext bench (`frappe` `15.126.0`, `erpnext` `15.124.5`, `hrms` `15.64.8`, `change_engine` `0.1.0`, MariaDB `10.6`, Redis `7.2.7-alpine`) against Phase 0 exit criteria `E0-1` through `E0-7` ([phase-exit-criteria.json](../specs/phase-exit-criteria.json), [phased-delivery-and-lanes.md](phased-delivery-and-lanes.md)).

All data in this report is synthetic (`p0a-*.localhost`, `p0b-*.localhost`, `Golden Trading Co`, `ITEM-001`, `CUST-001`).

## How to run

- **Offline contract and unit suite (CI):**
  ```bash
  PYTHONPATH=apps/engine/change_engine python3 -m unittest apps/engine/change_engine/change_engine/tests/test_erp_021_phase0_proofs.py -v
  ```
- **Live pinned bench suite:**
  ```bash
  python3 infra/dev/docker/run_phase0_proofs.py --compose-project platform-erp001-20261111b --engine-port 18111
  ```
  Implementation: [phase0_bench_proof.py](../../apps/engine/change_engine/change_engine/proofs/phase0_bench_proof.py) and [run_phase0_proofs.py](../../infra/dev/docker/run_phase0_proofs.py).

## Summary matrix

| Criterion | Scope proved | Live bench result | Notes |
|---|---|---|---|
| `E0-1` | Two-tenant isolation (DB creds, Frappe runtime, HTTP Host, `ChangeEngineAdapter`) | **PASS** | Cross-tenant SQL read/aggregate/write raise MariaDB `1142` permission errors; `Host` header spoof returns HTTP `403`. |
| `E0-2` | Golden Path trading sale (`100 @ 10.00` opening, `SO 10 @ 15.00`, `DN`, `SI update_stock=0`, 10% discount variant, `Q-23` cancel) | **PASS** | Closing Trial Balance nets to `1,150.00 == 1,150.00` (gross GL turnover `1,250.00 == 1,250.00`); `Bin` and AR tie out (`900.00`, `150.00`). |
| `E0-3` | Role denials, `CE-SEC-001`, Zone 2 GL lock, `Item.valuation_rate` masking, adapter fail-closed authz | **PASS** | Discovered default `Item.valuation_rate` `permlevel=0` exposure to `Sales User`; verified `Property Setter` `permlevel=1` mask blocks it. |
| `E0-4` | Interrupted guarded DDL/config change (`PREPARE`, Stage 4 `Error 1205` MDL timeout, Stage 6 finalize error, adapter execute fault) | **PASS** | Documented two `change_engine` findings (`MODIFY COLUMN` false drift on ERPNext `decimal(21,9)` tables; Stage 6 audit status gap). |
| `E0-5` | Duplicate-effect prevention (resubmit DN/SI, over-delivery, over-stock, DDL & adapter idempotency/conflict) | **PASS** | Double `.submit()` on submitted DN is a silent `update_after_submit` no-op (`0` extra `SLE`/`GL`), not an exception. |
| `E0-6` | Real Blueprint + `BPL-029` mapping + `ChangeEngineAdapter` + live `Custom Field` / `Property Setter` quarantine + `zatca_sa` Phase 1 | **PASS** | `BPL-029` checked across `36` mapped fields (`0` missing, `2` type mismatches: `Percent` vs engine `Float`). |
| `E0-7` | Engine limitations & alternatives catalogued | **RECORDED** | Seven concrete engine findings and mitigations documented below. |

## Detailed findings

### `E0-1` — Two-tenant isolation

Verified across two freshly provisioned synthetic sites (`site_a` in `SA`/`SAR`, `site_b` in `AE`/`AED`):
- **Database credential isolation:** Each site runs on its own MariaDB database and site DB user. Using site B's DB credentials to query `SELECT name FROM <db_a>.tabCustomer`, `SELECT COUNT(*)`, or `INSERT` into site A raises MariaDB `OperationalError(1142, ... denied ...)`, and symmetrically from site A to site B.
- **Runtime ORM isolation:** Inside `site_b`, `frappe.get_all("Customer")` returns `0` matches for site A's canary customer.
- **HTTP Host isolation:** `GET /api/method/ping` with valid `Host: <site_a>` and `Host: <site_b>` returns `200`, while querying site A's canary resource with `Host: <site_b>` returns `403`.
- **Adapter boundary isolation:** `ChangeEngineAdapter` keeps separate stores per `tenantId`, returns `tenant_not_found` for unknown tenants, and fails closed with `permission_denied` when `caller` service/identity is absent or unauthorized.

### `E0-2` — Reconciled trading transaction (`BPL-028`, `ADR-0033`, `Q-23`)

1. **Defaults vs explicit provisioning (`ADR-0033`, `Q-23`):**
   - Freshly created sites default to `Stock Settings.valuation_method = "FIFO"`, `System Settings.rounding_method = "Banker's Rounding (legacy)"`, and `Accounts Settings.enable_immutable_ledger = 0`.
   - Under default legacy rounding, `rounded(-0.105, 2)` and `flt(-0.105, 2)` return `-0.1` (asymmetric). After setting `Commercial Rounding`, both `rounded(-0.105, 2)` and `flt(-0.105, 2)` return `-0.11`, matching `+0.11`.
2. **Golden Path (`SO -> DN -> SI`):**
   - Opening `Stock Entry` (`Material Receipt`, `100 @ 10.00`): Dr `Stock In Hand` `1,000.00`, Cr `Capital Stock` `1,000.00`.
   - `Sales Order` (`10 @ 15.00 = 150.00`): `0` GL entries, `0` Stock Ledger entries.
   - `Delivery Note` (linked via `against_sales_order` and `so_detail`): Dr `Cost of Goods Sold` `100.00`, Cr `Stock In Hand` `100.00`. `Bin` moves to `actual_qty = 90.0`, `stock_value = 900.00`, `valuation_rate = 10.00`.
   - `Sales Invoice` (`update_stock = 0`): `0` Stock Ledger entries; Dr `Debtors` `150.00`, Cr `Sales` `150.00`; `outstanding_amount = 150.00`.
   - **Reconciliation:** Net closing Trial Balance totals `1,150.00 == 1,150.00` (matching [golden-path-trading-sale.md](../specs/golden-path-trading-sale.md)); gross period GL turnover totals `1,250.00 == 1,250.00`; Inventory GL balance (`900.00`) matches `Bin.stock_value` (`900.00`), and AR GL balance (`150.00`) matches `Sales Invoice.outstanding_amount` (`150.00`).
3. **10% Discount variant & `Q-23` immutable ledger cancellation:**
   - Second sale with `additional_discount_percentage = 10.0`: `SO.grand_total = 135.00`, `SI.grand_total = 135.00`, GL `Debtors` Dr `135.00` / `Sales` Cr `135.00`.
   - Cancelling the invoice with `Accounts Settings.enable_immutable_ledger = 1` preserves `4` GL rows (original + reversing entries with `is_cancelled = 1` audit trail) instead of deleting history. `Q-23` is confirmed viable on the bench and should be enabled by default in v1 provisioning (`ERP-003` / `ADR-0033` follow-up).

### `E0-3` — Denied operations and field masking

- **Role permissions enforced:** `Sales User` is denied `GL Entry` read and `get_list`; `Stock User` (warehouse) is denied `Sales Invoice` and `GL Entry`; `Accounts User` (finance) is denied permission mutation (`Custom DocPerm`).
- **Default cost-exposure finding & fix:** On a stock ERPNext site, `Item.valuation_rate` carries `permlevel = 0`, so `Sales User` can read item cost via `frappe.get_list("Item", fields=["name", "valuation_rate"])`. Creating a `Property Setter` setting `Item.valuation_rate` `permlevel = 1` strips `valuation_rate` from `Sales User` queries.
- **Change engine & adapter fail-closed:** Spoofed caller role on `apply_ddl_change` (`CE-SEC-001`) fails with `UNAUTHORIZED_ROLE`; DDL against Zone 2 (`GL Entry`) fails with `ZONE_SAFETY_VIOLATION`; unauthorized `ChangeEngineAdapter` caller fails with `permission_denied`.

### `E0-4` — Interrupted guarded change & recovery (`ADR-0028`)

- **Stage 3 prepare failure (`ToDo`):** Simulated `Custom Field` / audit failure aborts cleanly with `status = "FAILED_CLEAN"`, `stage = "PREPARE"`, leaving no orphan field or lock.
- **Stage 4 live MariaDB `Error 1205` MDL timeout (`ToDo`):** Holding an uncommitted `SELECT ... FOR UPDATE` transaction on `tabToDo` while `execute_single_field_deployment` executes DDL (`lock_wait_timeout = 2s`) fails on `ALTER TABLE` with MariaDB `(1205, 'Lock wait timeout exceeded')` after `Custom Field` metadata was already implicitly committed by MariaDB prior to the DDL wait. Reconciler enters `status = "RECOVERY_REQUIRED"`, `disposition = "ORPHAN_METADATA_NON_DESTRUCTIVE_HOLD"`, releases the MariaDB `GET_LOCK` advisory lock, and blocks subsequent deployments on `ToDo` fail-closed at `INSPECT`.
- **Stage 6 finalize failure (`Note`):** Injecting a persistence error after DDL succeeds returns `status = "RECOVERY_REQUIRED"`, `disposition = "VERIFIED_CONSISTENT"` with the added column intact. See finding #2 in `E0-7` below regarding the `tabChange Engine Audit` status row (`PREPARED` vs `RECOVERY_REQUIRED`).
- **Adapter fault injection (`ChangeEngineAdapter`):** Injecting an `execute` fault at step 1 triggers compensation (`status = "compensated"`), emits `1` event, restores `exportHash`, and leaves `dropped_data() == []`.

### `E0-5` — Duplicate-effect prevention

- **Live `Delivery Note` double `.submit()`:** Calling `.submit()` again on an already-submitted `Delivery Note` (`docstatus == 1`) does **not** raise `ValidationError` (`check_docstatus_transition` treats `1 -> 1` as `update_after_submit`); `SLE` and `GL Entry` counts remain unchanged (no duplicate stock or accounting effect), though the gateway must enforce idempotency keys rather than relying on the engine raising an error on double submit (`Q-16`).
- **Cancelled resubmit / over-delivery / over-stock:** Re-submitting a cancelled `Sales Invoice`, creating a second `Delivery Note` for an already-delivered `Sales Order`, and delivering `500` units when `90` are in stock (`allow_negative_stock = 0`) all raise `ValidationError` with zero extra ledger rows.
- **Guarded DDL & adapter idempotency:** Replaying `dep_p0_idemp_1` with matching inputs returns `ALREADY_APPLIED` (`NO_OP`); replaying with a different payload raises `IdempotencyConflictError`. `ChangeEngineAdapter` replays idempotently on identical keys and returns `idempotency_conflict` on payload mismatch.

### `E0-6` — Real Blueprint, `BPL-029` mapping, and `zatca_sa` component

- **Live metadata check (`BPL-029`):** Verified all `9` mapped DocTypes and `36` mapped fields from [engine-mapping-golden-path.json](../../contracts/examples/engine-mapping-golden-path.json) against live `frappe.get_meta(...)`: `0` missing DocTypes, `0` missing fields, and `2` fieldtype mismatches (`Sales Order.additional_discount_percentage` and `Sales Invoice.additional_discount_percentage` are `Float` in ERPNext `v15.124.5`, listed as `Percent` in the draft mapping).
- **Non-destructive quarantine & `zatca_sa`:** Adding a `Custom Field` on `Note`, writing `30`, and quarantining via `Property Setter` (`hidden = 1`) preserves the stored value (`30`), matching `ChangeEngineAdapter` `field.quarantine` behavior (`dropped_data() == []`). Invoking [components/compliance/zatca_sa/phase1.py](../../components/compliance/zatca_sa/phase1.py) on the Golden Path invoice totals produces a valid Phase 1 Base64 TLV QR payload.

### `E0-7` — Engine limitations and alternatives (recorded)

1. **`ddl_plan_gate.py` false `MODIFY COLUMN` drift on core ERPNext `decimal(21,9)` tables:** In MariaDB `10.6`, `decimal(21,9)` columns with default `0` report `COLUMN_DEFAULT = '0.000000000'` in `INFORMATION_SCHEMA`, whereas Frappe DocFields have `default = None`. Live `MariaDBTable.alter()` emits false `MODIFY ... decimal(21,9) not null default 0` statements on `Customer`, `Sales Order`, `Delivery Note`, `Sales Invoice`, and `Item`, causing `validate_ddl_plan` to reject additive custom fields (`QUEUE_FOR_CONTROLLED_ADMIN_DEPLOYMENT`). *Alternative/fix:* normalize `MariaDBTable` decimal default comparisons (matching `SimulatedDbColumn`) before `BPL-007` enables automated custom fields on core trading DocTypes.
2. **Stage 6 finalize fault leaves `tabChange Engine Audit.status = 'PREPARED'`:** When Stage 6 persistence fails after Stage 4 DDL succeeds, `execute_single_field_deployment` returns `RECOVERY_REQUIRED`, but `tabChange Engine Audit` keeps `status = 'PREPARED'` instead of rolling/reconciling to `RECOVERY_REQUIRED`, so subsequent `is_target_in_recovery_required` checks (which query `status = 'RECOVERY_REQUIRED'`) would miss a Stage 6 finalize failure unless reconciled. *Alternative/fix:* record/update a `RECOVERY_REQUIRED` marker in a separate commit/status handler before returning, or treat stale `PREPARED` rows as recovery-blocking in `ERP-012`/`BPL-007`.
3. **Frappe `.submit()` on `docstatus == 1` is silent (`update_after_submit`), not rejected (`Q-16`):** Gateway/adapter endpoints must require operation-scoped idempotency keys for submit transitions (`PLT-024` / `ERP-012`) rather than expecting an engine exception on duplicate submits.
4. **`Item.valuation_rate` `permlevel = 0` exposure to `Sales User`:** Tenant provisioning (`ERP-003`) or base Blueprint compilation (`BPL-004`/`ERP-008`) must apply `Property Setter` `permlevel = 1` on cost/valuation fields (`Item.valuation_rate`, `Stock Ledger Entry`, `Bin.valuation_rate`, etc.) so `Sales User` cannot read costs.
5. **Provisioning defaults differ from `ADR-0033` and `Q-23`:** `FIFO`, `Banker's Rounding (legacy)` (asymmetric `-0.105 -> -0.10`), and `enable_immutable_ledger = 0` are active on every new Frappe/ERPNext site until explicitly overridden during provisioning (`ERP-003`).
6. **`BPL-029` mapping type drift:** `Sales Order.additional_discount_percentage` and `Sales Invoice.additional_discount_percentage` are `Float` in live ERPNext `v15.124.5`, not `Percent`. Needs alignment in `BPL-029` (`contracts/examples/engine-mapping-golden-path.json`, Eldon's lane).
7. **Sequential site provisioning latency:** `bench new-site --install-app erpnext --install-app hrms --install-app change_engine` takes ~4–4.5 minutes per site on the pinned single-container dev bench (`ERP-002` load spike will need warm pool / template DB cloning evaluation).
