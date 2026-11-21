# Session log: erp-015-q514-decision

Date: 2026-11-21
Author: partner
Tool and model: claude-code (Claude Opus 5.5)
Plan IDs: ERP-015,ERP-031

## Summary
Q-514 is decided by the partner (2026-11-21, option 2 for both), and the ERP-015 tests now assert both rules instead of carrying them as expected failures. This changes tests and docs only; no product code changed. ERP-015 is `done`, and the live CI wiring moves to the new row ERP-031.

Decided v1 valuation behaviour, as the tests now state it:
- (a) A sales return (a delivery return against its delivery) comes back at the warehouse's current moving-average cost, not at the cost its delivery booked. In the fixture, 5 units leave at 575.00 and come back at 627.94 (5 x 2135.00 / 17). The GL moves the same 627.94 from COGS back to Stock In Hand.
- (b) Quantities keep the engine's default precision: `System Settings.float_precision` stays unset. Quantity fields accept 3 decimals, and the stock ledger stores the running quantity rounded half up to 2 decimals. 12.345 Kg received at 10.00 is stored as 12.35 Kg worth 123.45, rate 9.995951417. Issuing the 12.345 Kg leaves exactly zero.

Where the rules are written down: here, in the PR body and in the ERP-015 test module docstring. The trading scope spec (other founder's lane) and ADR-0033 (accepted) are not edited. A founder may want to record the rules there by a separate change.

## Files touched
- `apps/engine/change_engine/change_engine/tests/test_erp_015_inventory_valuation.py`:
  - The docstring states both decided rules.
  - The oracle drops the alternative "delivery cost" sales-return rule and `V1_SALES_RETURN`. It now models the 2-decimal stored quantity with `stored_qty`: the exact sum of the moved quantities, rounded half up to `QTY_PLACES = 2`. Rates are value / stored quantity, and the final book holds stored quantities.
  - The g6 entry in `FORCED_EXACT` is now a hand-computed expectation under the decided rule, no longer a regression pin.
  - Pure layer: the oracle test asserts q1 (12.345 moved, 12.35 stored, 123.45, rate 9.995951417) and q2. It also asserts that g6 differs from the delivery's cost and that `stored_qty` rounds half up. The checker gets two new defect cases: "sales return at the delivery's cost" and "quantity stored to 3 decimals".
  - Live layer: `test_6_sales_return_comes_back_at_the_current_moving_average` checks g3 and g6 in the SLE and their Stock In Hand and COGS GL rows. `test_7_three_decimal_quantities_are_stored_to_two_decimals` checks that `float_precision` is unset, q1 is at 12.35 and 9.995951417, and the full oracle check passes for E15-QTY. `test_8` keeps the exact five-field baseline for q1 and q2. Both tests are normal tests now, and the `_not_the_known_mismatch` helper is removed.
- `docs/open-questions.md`:
  - Q-514 is marked RESOLVED (decider partner, 2026-11-21).
  - New Q-555 on the repost job rewriting GL rows under the immutable ledger.
- `docs/PLAN.md`:
  - ERP-015 is `done`.
  - New row ERP-031 (live valuation layers in real-bench CI), placed after ERP-029. ERP-030 is not on main: it exists only in the open PR on `erp-016-branded-document-templates`, which puts it after ERP-016.
- Merged `origin/main` (clean, no conflicts).

## Decisions
- Q-514 (a) and (b), partner, 2026-11-21: see the summary. No ADR (these are confirmations of engine defaults under ADR-0033). The oracle's model of (b) is fitted to the observed figures, a full receipt and a full issue of 12.345 Kg. A partial issue of a 3-decimal quantity is not covered: UNVERIFIED.

## Checks
- ERP-015 offline: OK. ERP-014: OK (skipped=7). `pytest scripts/tests`: 22 passed.
- `check_docs`: 0 errors. `check_repo_hygiene`: OK. `scan_secrets`: 0 hits. `check_plan_independence`: OK. `check_lanes --actor partner`: OK.
- Live: new throwaway Compose project `erp015r3-a16a48` (no host DB port; engine on a random 127.0.0.1 port), fresh synthetic site `erp015r3a.localhost` with `tenant_id` set, `REQUIRE_ERP015_LIVE=1`: 18 tests, OK, no expected failures (live test_0 to test_9 and the 8 pure tests all pass). Teardown: only `erp015r3-a16a48` was removed, with its volumes.

## Tokens or cost
Unknown.

## Next step
- ERP-031 (partner): run the ERP-014 and ERP-015 live layers in the real-bench runner. The runner sets `tenant_id` on its site, and `REQUIRE_ERP015_LIVE=1` stops the layers from skipping.
- Q-555: the founders decide whether the repost job may rewrite the GL rows of reposted vouchers under the immutable-ledger intent of Q-23.
