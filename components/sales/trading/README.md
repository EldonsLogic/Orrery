# Trading and distribution pack

Status: tested locally; sandbox candidate, pending CI integration and independent review
Owner: partner
Plan IDs: ERP-011, ERP-028

`sales.trading_distribution@0.1.0` is an internal native-document configuration library for the [ERP-005 scope](../../../docs/specs/core-module-scope-trading.md). It reuses the installed engine; no upstream source, runtime dependencies, customer-specific code or financial calculations are included. Its own licence is `LicenseRef-Proprietary`; engine licences remain recorded in [NOTICE.md](../../../NOTICE.md).

| Capability | Native records | Boundary |
|---|---|---|
| Selling prices | Price List, Item Price, Pricing Rule, Selling Settings | Create selling-only lists, explicit UOM prices and company/item/list quantity discounts; disable manual list-rate editing |
| Customer credit | Customer.credit_limits / Customer Credit Limit | Upsert one positive company limit; preserve other companies; set the Sales Order bypass flag to zero |
| Rep commission | Sales Person, Sales Order.sales_team / Sales Team | Set master percentage and draft-order attribution; use engine-computed informational amounts |

`TradingPack(engine)` takes the trusted host's request-bound engine module. Supply no site, user or role from request input. It binds the current site/user, rechecks both before writes, uses native document permissions, checks field access (including credit child fields), and calls ordinary `insert()` / `save()`. It never switches sites/users, commits, submits transactions, uses permission bypasses, or returns documents/credit balances. Return values are record IDs; validation errors are keys in `strings.json`. Native errors still require the host's existing error sanitization boundary.

Each call writes one native document. The host owns approvals, transaction rollback, native audit capture and concurrency handling. Create calls use native duplicate checks and naming; they are not replay-safe activation commands. Credit updates reload the parent and preserve native optimistic concurrency checks. Creation of a price list also requires Selling Settings write access because its native hook can set the default list.

Commission amounts are **informational estimates**, not earned/payable/accrued commissions. No settlement policy, GL entry, payment, payroll, tax or commission formula is provided. Rate changes apply to future attribution; attribution changes require a draft Sales Order and valid enabled leaf reps, with unique positive shares totalling 100 percent. The engine computes contribution and incentives when saving. An accountant must review the treatment before promotion or settlement integration.

## Verification and certification

From the repository root, with the existing Blueprint test dependencies installed:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=components/sales/trading python3 -m pytest components/sales/trading/tests -q
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=services/blueprint python3 -m factory check components/sales/trading --run-tests --trusted-source --out /tmp/erp011-factory.json
```

The factory runs the declared boundary suite in an isolated copy and scrubbed environment; its logical sandbox does not grant production certification. The manifest declares the local factory's maximum attained level, `tested`, and conservatively flags accounting sensitivity with `touchesLedgerOrTax: true`. No reviewer, CI evidence, canary, Arabic/RTL verification or production certification is claimed. The existing CI workflow does **not** invoke this pack yet; ERP-028 must wire it before publication under the library's CI rule.

The rollback-only native proof is `tests/bench_trading.py:run(engine)`. Invoke it from a trusted connected synthetic bench runner with this folder and its `tests/` on the Python path. It creates fixtures using native APIs, checks price/discount/credit/commission saves and a real authenticated permission denial, then rolls back on success or failure. This was run on Frappe 15.126.0, ERPNext 15.124.5 and HRMS 15.64.8; package version strings were inspected in the container. Source commit identity in that image is UNVERIFIED. The compatibility entry records this local native run, not CI certification. No stock or submitted-sale flow was tested.

## Activation dependency and limits

- **ERP-028:** `FrappeRuntimeBackend.execute_step()` currently has no `component.enable`, `component.configure` or `component.disable` handlers. All three return without native document calls (source inspection and instrumented probe recorded in the session log). This library is not automatically invoked by the compiler or runtime; binding its manifest does not activate it. ERP-011 stays `doing` pending merge; this PR prepares the pack only.
- The separate fictional `sales.price_list@0.1.0` manifest supplies `price_list` and `price_list_item` entity artifacts to the trading fixture. This pack uses a distinct ID and function artifacts, preserving that fixture. It is not a drop-in replacement; fixture/mapping migration belongs to ERP-028, with the spine owner reviewing the interface.
- Credit configuration is not proof of secured credit enforcement. Existing `Accounts Settings.credit_controller` exemptions are unchanged. The existing policy guard explicitly targets Sales Order only. Sales Invoice, Delivery Note, exposure/receivables, exemptions and concurrent submissions need end-to-end tests before any enforcement claim.
- No discount-approval workflow is implemented or claimed. Native pricing configuration saves were tested; applying discounts in submitted sales, approval binding and recovery remain ERP-028 / ERP-023 integration work.
- Batches, serials, landed costs and Sales Partner remain outside this pack, as optional/proposed ERP-005 scope. No production activation, country compliance or phase exit is claimed. Native Arabic copy and RTL review remain prerequisites for promotion.
