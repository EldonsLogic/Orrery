# Session log: erp-014-accounting-property-tests

Date: 2026-11-18
Author: partner
Tool and model: claude-code / opus-5.5
Plan IDs: ERP-014

## Summary
Added seeded accounting property tests. They cover five things: every voucher balances, VAT follows the engine's documented rounding rule (KSA 15%, UAE 5%, with zero-rated and exempt lines mixed in), rounding is half away from zero with no float drift, cancel and credit note exactly negate, and stock value ties to Stock In Hand. They ran green against a throwaway synthetic site on my own bench. No engine defect was found, so nothing is recorded as xfail.

## Files touched
- `apps/engine/change_engine/change_engine/tests/test_erp_014_accounting_properties.py`: two layers. The pure layer runs in CI and checks the decimal oracle and the invariant checkers against ADR-0033 evidence and seeded data. The live layer skips with a reason unless `ERP014_COMPOSE_PROJECT` and `ERP014_SITE` are set.
- `apps/engine/change_engine/change_engine/tests/erp_014_bench_probe.py`: runs inside the bench. It posts seeded synthetic vouchers in two companies (SAR and AED) and dumps amounts as decimal strings (`CAST(... AS CHAR)`). It makes no assertions and refuses a site that already holds its postings.
- `infra/dev/docker/tests/test_erp_014_accounting_properties.py`: a `load_tests` loader, so the existing CI step (`unittest discover` in `infra/dev/docker`) runs the pure layer. No `.github/` edit was needed.
- `docs/PLAN.md`: ERP-014 set to done.

## What the tests check
1. Balance: per (company, voucher type, voucher) sum debit == sum credit, exactly in Decimal, company currency, over every GL row of both companies (invoices, credit notes, cancellations, stock entries).
2. VAT: with `round_row_wise_tax = 0` (asserted), the engine leaves each line's tax (line net × rate / 100) unrounded, sums the lines and rounds the row total once (`erpnext/controllers/taxes_and_totals.py`, `calculate_taxes` and `round_off_totals`, read on the pinned bench). The tests assert three things. The stored tax equals that value exactly. It is within 0.005 × lines of rounding each line separately. Grand total = net total + tax. Zero-rated and exempt lines use Item Tax Templates at 0% and add no tax.
3. Rounding: `System Settings.rounding_method = Commercial Rounding` (ADR-0033). The engine's `flt(x, 2)` equals Decimal ROUND_HALF_UP (half away from zero) on ±x.xx5 samples, including the ADR-0033 values. Totals are equal for the same lines in shuffled order. Every GL and total amount is a whole cent.
4. Negation: under the immutable ledger, the rows of a cancelled invoice pair up exactly (same account, debit and credit swapped). The same holds for an invoice plus its full credit note. The credit note's tax and grand total are exactly the negatives. Kept invoices are not mirrored.
5. Stock: golden path figures: opening 100 at 10.00 = 1,000.00, then after 10 leave, 90 = 900.00. After seeded Moving Average receipts and issues, Bin value = sum of SLE value differences = GL balance of Stock In Hand.

Rates: KSA 15% and UAE 5% were confirmed from official-domain search results (zatca.gov.sa guidelines; tax.gov.ae FAQ and Decree-Law 8/2017 Art. 3), read 2026-11-18. The documents themselves were not fetched, so treat the rates as SECONDARY. The tests only set the template rate; the engine applies it.

## Verification
- Pure layer: `PYTHONPATH=apps/engine/change_engine python3 -m unittest apps/engine/change_engine/change_engine/tests/test_erp_014_accounting_properties.py`: 5 passed, 7 skipped (no bench). The loader run via `cd infra/dev/docker && python3 -m unittest discover -s tests -p "test_erp_014*"` gave the same result.
- Live layer: own Compose project `erp014-props` (port 18414, random synthetic passwords kept outside the repo), fresh site, `ERP014_EXAMPLES=30` (60 invoices across SAR and AED, 31 stock moves, 130 rounding samples): 12 of 12 passed in 123 s. An earlier run with the default 6 examples passed every invariant on a reused site. My project and its volumes were removed afterwards with `down -v`.

## Findings for provisioning (not defects in ledger maths)
- A Company created outside the setup wizard (the AED company here) has no default income account, receivable account or round-off account. Invoices then fail to submit ("Please mention Round Off Account"). ERP-003 provisioning should set these explicitly for every company.
- A line-level `item_tax_rate` JSON is overwritten on insert. Zero-rated and exempt lines need an Item Tax Template, or they are silently taxed at the full rate. Country packs (CMP-006, CMP-021) must use templates.

## Not done or not verified
- No accountant review of the oracle or of the VAT rule. A human or accountant should confirm the "round once per tax row" rule is acceptable for ZATCA and FTA. ZATCA's per-line rounding expectations are UNVERIFIED here.
- Discounts, multi-currency invoices (foreign currency on a company), purchase-side documents, Payment Entry and partial credit notes are not covered. ERP-015 covers valuation depth.
- Zero-rated and exempt are only checked as 0% arithmetic. Their reporting and input-tax treatment is not tested.
- The live layer needs a disposable site and is not in CI (no shared bench, ADR-0018). Only the pure layer runs in CI.
- Shared machine note: after my teardown the `erp002-load-spike` containers were no longer listed. My compose commands were all scoped to `erp014-props`, and the `down` output listed only `erp014-props` resources. I did not stop them, but I could not confirm who did.

## Decisions
- No new dependency: seeded stdlib `random` instead of a property-testing library, so no licence to record.

## Tokens or cost
Unknown.

## Next step
ERP-015 (inventory valuation correctness). ERP-003 to set per-company default and round-off accounts. Accountant review of the VAT rounding rule (LEG-019 reviewer search).
