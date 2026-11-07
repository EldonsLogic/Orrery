# Blueprint fixtures

Status: draft
Owner: eldon

Hand-written reference Blueprint for a fictional Saudi trading and distribution company, plus one fake component manifest per component it uses. It is the shared input for the Blueprint validator, the compiler snapshot tests (QA-004) and the trading template (DSC-002).

All data is fictional. The company, its CR number (1010000000), VAT number (300000000000003), reviewer and owner handles, import job ids and interview turn ids are invented and belong to no real organisation or person. The component manifests describe no real component and ship no code.

## Files
| File | Purpose |
|---|---|
| `trading-distribution.blueprint.json` | The Blueprint. Valid against `contracts/blueprint.schema.json` and written to satisfy every rule in its `x-validator-rules`. |
| `registry/<component id>.json` | 16 fake manifests, one per entry in the Blueprint's `components`. Each is valid against `contracts/component.manifest.schema.json`, version 0.1.0, and lists every `computed.function` the Blueprint uses under `provides` (artifact type `function`). |

## What the fixture models
Al Waha Distribution Trading Co. (Arabic: شركة الواحة للتوزيع التجاري), 25-49 staff, with a Riyadh head office, a Jeddah branch, a warehouse in each city and a finance department. Arabic is the default locale, English is secondary. The company is VAT registered (15 percent, monthly filing) and issues ZATCA phase 2 e-invoices in the sandbox environment. Company locale is fully specified: Asia/Riyadh, Gregorian primary with Hijri (Umm al-Qura) secondary display, week starting Sunday, Friday and Saturday weekend, Ramadan reduced hours, Gregorian fiscal year, `sa.holidays` calendar with one company override, Western digits, SAR.

### Locations
| Id | Kind | Parent |
|---|---|---|
| `hq_riyadh` | branch | |
| `branch_jeddah` | branch | |
| `wh_riyadh` | warehouse | `hq_riyadh` |
| `wh_jeddah` | warehouse | `branch_jeddah` |
| `dept_finance` | department | `hq_riyadh` |

### Entities (24: 14 top-level, 10 child line tables; 189 fields)
| Entity | Kind | Workflow | Bound components | Provenance |
|---|---|---|---|---|
| `customer` | master | | core.customer | interview, human edited (owner) |
| `supplier` | master | | core.supplier | template |
| `item` | master | | core.item, stock.ledger (extends) | template |
| `price_list` (+ `price_list_item`) | master | | sales.price_list | imported, human edited (team reviewer) |
| `sales_quote` (+ line) | document | | sales.quote | template |
| `sales_order` (+ line) | document | `sales_order_flow` | core.sales_order | interview |
| `delivery_note` (+ line) | document | | sales.delivery_note, stock.ledger (extends) | template |
| `sales_invoice` (+ line) | document | `sales_invoice_flow` | core.sales_invoice, compliance.zatca_sa (extends) | template |
| `credit_note` (+ line) | document | | sales.credit_note, compliance.zatca_sa (extends) | interview |
| `purchase_order` (+ line) | document | `purchase_order_flow` | purchasing.purchase_order | template, human edited (owner) |
| `purchase_receipt` (+ line) | document | | purchasing.purchase_receipt, stock.ledger (extends) | template |
| `purchase_invoice` (+ line) | document | | purchasing.purchase_invoice | template |
| `payment` | document | | finance.payment_entry | template |
| `stock_transfer` (+ line) | document | `stock_transfer_flow` | stock.transfer, stock.ledger (extends) | manual, human edited (team reviewer) |

Child entities carry the binding of their parent's primary component. Money fields all use precision 2. Totals, VAT, due dates, outstanding balances, stock on hand and the ZATCA QR payload are computed fields that name a function (30 distinct functions); there are no formulas anywhere.

### Workflows (4, 24 transitions)
| Workflow | States | Notes |
|---|---|---|
| `sales_order_flow` | draft, pending_approval, approved, delivered, invoiced (final), cancelled (final) | Three submit paths split on total (50,000 SAR) and discount (10 percent); approvals attached to the approve transitions |
| `purchase_order_flow` | draft, pending_approval, ordered, received, closed (final), cancelled (final) | Over 100,000 SAR goes to two-step approval |
| `sales_invoice_flow` | draft, submitted, paid (final), cancelled (final) | `mark_paid` guarded on outstanding amount |
| `stock_transfer_flow` | draft, in_transit, received (final) | Dispatch guarded on both warehouses being set |

### Roles (8)
| Role | Function | Scope | Notes |
|---|---|---|---|
| `owner` | owner | company | admin; second approver on large purchase orders |
| `general_manager` | general_manager | company | approves large sales orders, discounts and the first purchase step |
| `accountant` | finance | company | issues invoices, approves credit notes, only role that sees `vat_summary` |
| `sales_rep` | sales | own_records | `cost_price` and `credit_limit` hidden |
| `branch_sales_manager` | sales | branch: `branch_jeddah` | Jeddah rows only |
| `purchasing_officer` | purchasing | company | raises and submits purchase orders |
| `warehouse_keeper` | warehouse | warehouse: `wh_riyadh`, `wh_jeddah` | cost and selling price hidden |
| `auditor` | read_only | company | read and export only, chat actions off |

### Approvals (4)
| Id | Applies to | Condition | Steps |
|---|---|---|---|
| `large_sales_order_approval` | sales_order submit | total_amount > 50,000 | general_manager (escalates to owner) |
| `discount_approval` | sales_order submit | discount_percent > 10 | general_manager (escalates to owner) |
| `po_large_approval` | purchase_order submit | total_amount > 100,000 | 1 general_manager, 2 owner |
| `credit_note_approval` | credit_note submit | any amount | accountant (escalates to general_manager) |

All have `selfApproval` false, and no approver role also holds `submit` on the entity it approves.

### Reports (6)
| Id | Kind | Entity | Visible to |
|---|---|---|---|
| `sales_overview` | dashboard | sales_order | owner, general_manager, branch_sales_manager, auditor |
| `receivables_aging` | report | sales_invoice | owner, general_manager, accountant, auditor |
| `payables_aging` | report | purchase_invoice | owner, general_manager, accountant, purchasing_officer, auditor |
| `stock_on_hand` | report | none | owner, general_manager, purchasing_officer, warehouse_keeper, auditor |
| `vat_summary` | report | sales_invoice | accountant |
| `my_orders` | report | sales_order | sales_rep |

### Integrations (2)
`customer_list_upload` (`file.excel_upload`, tier 2, manual, 5 mappings into `customer`) and `bank_statement_import` (`file.bank_statement_csv`, tier 2, manual, 5 mappings into `payment`).

### Branding
Primary `#0F8A7E` and accent `#B8741A`. Contrast ratios (WCAG 2.x relative luminance) against the surfaces in `docs/brand/tokens/tokens.json`:

| Colour | Light surface #FFFFFF | Light background #F3F4F6 | Dark surface #171B23 | Dark background #0E1117 |
|---|---|---|---|---|
| Primary `#0F8A7E` | 4.24 | 3.85 | 4.07 | 4.46 |
| Accent `#B8741A` | 3.78 | 3.44 | 4.56 | 5.00 |

Every ratio is at least 3:1. No logo is set because a logo needs a stored asset record; `poweredBy.show` is true.

## Deliberately simplified
- No `debit_note`, batches, serial numbers, multi-currency, landed cost, returns to supplier, or stock counts.
- The `stock.ledger` component has no entity of its own; it extends item, delivery note, purchase receipt and stock transfer. Stock on hand by warehouse therefore has no report `entity`, and its `groupBy` and filter use `warehouse` as a semantic-layer dimension.
- Credit notes have no workflow; the approval rule alone gates `submit`.
- Computed subtotals take `discount_percent` as their declared input; aggregation over child lines is implied by the `child_table` relation, since the schema does not say whether `inputs` may name a relation.
- Permissions are given on top-level entities only; child tables inherit their parent's permissions.
- The Blueprint does not use the `dept_finance` department in any role scope; it exists to cover all three location kinds.
- Metric ids (`sales.revenue`, `finance.receivables_aging`, `vat.net_payable`, and so on) are plausible names; no semantic-layer registry exists yet to check them against.
- Manifests use certification level `reviewed` (components touching ledger or tax) or `tested` (others) as placeholders; they carry no evidence.
- The engine adapter id is `change_engine`, not the engine's product name, because the repo hygiene gate bans the engine name on fixture paths (ADR-0016). `contracts/examples/blueprint-trading-minimal.json` uses a different adapter id; reconcile when the adapter id is fixed.
