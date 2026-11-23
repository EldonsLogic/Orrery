# Session log: erp-015-inventory-valuation-tests

Date: 2026-11-21
Author: partner
Tool and model: claude-code (Claude Opus 5.5)
Plan IDs: ERP-015

## Summary
Inventory valuation correctness tests for v1 trading (Moving Average and Commercial Rounding, ADR-0033). There are two layers. A Decimal oracle and checker run offline in CI. A bench probe runs only when `ERP015_COMPOSE_PROJECT` and `ERP015_BENCH_SITE` are set. The bench run passed, with two engine behaviours kept as expected failures until the open question Q-514 is answered. This session resumed an earlier session that hit a rate limit. Its work was saved in a local rescue commit, which was reviewed and finished here; the rescue commit itself was not pushed.

## Coverage
Every expected value is computed in Decimal from first principles, never with the engine's valuation code.
- Moving Average with receipts at different rates, then issues and deliveries. The ADR-0033 bench figures are checked exactly: rates 115 and 126.25, and a delivery cost of 575.00 where FIFO would give 500.00.
- Stock value equals the running sum of the stock ledger value differences for each item and warehouse. Bins match the last ledger row.
- The stock ledger ties to the GL. Each voucher's Stock In Hand movement equals its ledger total, the opposite account mirrors it (Stock Received But Not Billed, COGS or Stock Adjustment), every voucher balances, and all GL amounts are whole cents.
- Purchase returns leave at their receipt rate. Cancellations (a receipt and a transfer) reverse every GL row exactly.
- An issue beyond the stock on hand, or from zero stock, is rejected with no ledger rows left behind (`allow_negative_stock = 0`).
- Rounding: half-cent stock values (1.005 and 4.005) round to 1.01 and 4.01, not banker's 1.00 and 4.00. A seeded 40-move sequence (seed 15015) across two warehouses issues everything back to exactly 0.00, so no drift builds up.
- Transfers across three warehouses keep the company total. The destination receives exactly what the source books out.
- A Stock Reconciliation can change the rate alone, or the quantity and the rate.
- The checker is shown to catch these defects: a one-cent error, FIFO, banker's rounding, drift, a cancellation left active, a transfer leak, negative stock, a wrong rate, an unrounded value and a bin mismatch.
- Not covered, because they are out of v1 scope: FIFO and LIFO, Landed Cost Voucher, batches and serial numbers, back-dated reposting, and multi-currency purchases.

## Bench run
- Ran on the throwaway Compose project `erp015-val` (pinned dev bench; MariaDB is internal to the project, not 127.0.0.1:3306), on a fresh synthetic site `erp015e.localhost`.
- Result: 15 tests, 6 live tests pass, 2 expected failures.
- The expected failures were checked against the site's ledger to confirm the reason:
  - `test_6`, Q-514 (a). The sales return of 5 units came back at 627.94, the current moving average. The delivery had booked 575.00.
  - `test_7`, Q-514 (b). With `float_precision` unset, receiving 12.345 Kg left the running quantity at 12.35 and the rate at 9.995951417 instead of 10.00. The Q-514 wording from the interrupted session was corrected to match this evidence.

## Files touched
- `apps/engine/change_engine/change_engine/tests/test_erp_015_inventory_valuation.py`: new. Oracle, checker, pure tests and the live layer.
- `apps/engine/change_engine/change_engine/tests/erp_015_bench_probe.py`: new. In-bench probe that posts synthetic moves and dumps the SLE, bins and GL as decimal strings.
- `.github/workflows/tests.yml`: one engine-suite step for the offline file.
- `docs/open-questions.md`: Q-514.
- `docs/PLAN.md`: ERP-015 set to done.

## Decisions
- None. Q-514 is open for the founders and the accountant (LEG-019 reviewer): (a) how a sales return is valued, (b) the quantity precision provisioning sets (ERP-003).

## Tokens or cost
Unknown.

## Next step
- Answer Q-514. Then turn `test_6` and `test_7` into normal tests, or change them to match the decision (ERP-003 if provisioning sets `float_precision`).
- Cross-model review of this PR (Tier 3, ledger-adjacent).
