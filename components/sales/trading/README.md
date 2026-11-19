# Trading and distribution pack

Status: tested locally; CI workflow wired, pending independent founder review
Owner: partner
Plan IDs: ERP-011, ERP-028

`sales.trading_distribution@0.1.0` is an internal native-document configuration library for the [ERP-005 scope](../../../docs/specs/core-module-scope-trading.md). It reuses the installed engine; no upstream source, runtime dependencies, customer-specific code or financial calculations are included. Its own licence is `LicenseRef-Proprietary`; engine licences remain recorded in [NOTICE.md](../../../NOTICE.md).

| Capability | Native records | Boundary |
|---|---|---|
| Selling prices | Price List, Item Price, Pricing Rule, Selling Settings | Create selling-only lists, explicit UOM prices and company/item/list quantity discounts (`< 100%`); disable manual list-rate editing |
| Customer credit | Customer.credit_limits / Customer Credit Limit | Upsert one positive company limit (credit-authorising session role required); preserve other companies; set the Sales Order bypass flag to zero |
| Rep commission | Sales Person, Sales Order.sales_team / Sales Team | Set master percentage and draft-order attribution; use engine-computed informational amounts |

`TradingPack(engine)` takes the trusted host's request-bound engine module. Supply no site, user or role from request input. It binds the current site/user, rechecks both before writes, uses native document permissions, checks field access (including credit, sales-team, pricing-rule item and default-price-list fields), and calls ordinary `insert()` / `save()`. Because stock ERPNext grants `Sales User` `permlevel=0` write access on `Customer` and `Customer Credit Limit`, `set_credit_limit()` additionally checks the session's active roles via `engine.get_roles()` and fails closed with `TRD-ROLE` unless the caller holds `Credit Controller`, `Accounts Manager`, or `System Manager` (ADR-0027 human-floor safeguard; full approval workflow binding belongs to ERP-008 / ERP-023 / ERP-028). It never switches sites/users, commits, submits transactions, uses permission bypasses, or returns documents/credit balances. Return values are record IDs; validation errors are keys in `strings.json`. Native errors still require the host's existing error sanitization boundary.

Each call writes one native document. The host owns approvals, transaction rollback, native audit capture and concurrency handling. Create calls (`create_price_list`, `create_item_price`, `create_volume_discount`) use native duplicate checks and naming; they are not replay-safe activation commands and ERP-028 must provide keyed upserts plus journal and recovery tests before activation (ADR-0028). Credit updates reload the parent and preserve native optimistic concurrency checks. Creation of a price list also requires Selling Settings write access because its native hook can set the default list.

Commission amounts are **informational estimates**, not earned/payable/accrued commissions. No settlement policy, GL entry, payment, payroll, tax or commission formula is provided. Rate changes apply to future attribution; attribution changes require a draft Sales Order and valid enabled leaf reps with valid master commission rates, with unique positive shares totalling 100 percent. The engine computes contribution and incentives when saving. An accountant must review the treatment before promotion or settlement integration.

## Verification and certification

From the repository root, with the existing Blueprint test dependencies installed:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=components/sales/trading python3 -m pytest components/sales/trading/tests -q
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=services/blueprint python3 -m factory check components/sales/trading --run-tests --trusted-source --out /tmp/erp011-factory.json
```

Both checks are wired into `.github/workflows/tests.yml`. The factory runs the declared boundary suite in an isolated copy and scrubbed environment; its logical sandbox does not grant production certification. The manifest declares the local factory's maximum attained level, `tested`, and conservatively flags accounting sensitivity with `touchesLedgerOrTax: true`. No reviewer, canary, Arabic/RTL verification or production certification is claimed.

The rollback-only native proof is `tests/bench_trading.py:run(engine)`. Invoke it from a trusted connected synthetic bench runner with this folder and its `tests/` on the Python path. It creates fixtures using native APIs, checks price/discount/credit/commission saves, a real authenticated permission denial, and a stock `Sales User` credit-limit role denial (`TRD-ROLE`), then rolls back on success or failure (post-run DB checks confirm zero synthetic fixtures persist across savepoint rollback). This was run on Frappe 15.126.0, ERPNext 15.124.5 and HRMS 15.64.8; package version strings were inspected in the container. Source commit identity in that image is UNVERIFIED. The compatibility entry records this local native run, not CI certification. No stock or submitted-sale flow was tested.

## Activation dependency and limits

- **ERP-028:** `FrappeRuntimeBackend.execute_step()` currently has no `component.enable`, `component.configure` or `component.disable` handlers. All three return without native document calls (source inspection and instrumented probe recorded in the session log). This library is not automatically invoked by the compiler or runtime; binding its manifest does not activate it. Before activation, ERP-028 must add keyed upserts for `create_*` operations plus journal and recovery tests (ADR-0028), and decide whether Pricing Rule priority/validity windows are exposed. ERP-011 stays `doing` pending merge; this PR prepares the pack only.
- The separate fictional `sales.price_list@0.1.0` manifest supplies `price_list` and `price_list_item` entity artifacts to the trading fixture. This pack uses a distinct ID and function artifacts, preserving that fixture. It is not a drop-in replacement; fixture/mapping migration belongs to ERP-028, with the spine owner reviewing the interface.
- Credit configuration is not proof of secured credit enforcement. Existing `Accounts Settings.credit_controller` exemptions are unchanged. The existing policy guard explicitly targets Sales Order only. Sales Invoice, Delivery Note, exposure/receivables, exemptions and concurrent submissions need end-to-end tests before any enforcement claim.
- No discount-approval workflow is implemented or claimed. Native pricing configuration saves were tested; applying discounts in submitted sales, approval binding and recovery remain ERP-028 / ERP-023 integration work.
- Batches, serials, landed costs and Sales Partner remain outside this pack, as optional/proposed ERP-005 scope. No production activation, country compliance or phase exit is claimed. Native Arabic copy (all entries in `strings.json` are marked `"review": "unreviewed"` per ADR-0033) and RTL review remain prerequisites for promotion.
