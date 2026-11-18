# Session log: cmp-006-ksa-coa-tax-codes

Date: 2026-11-18
Author: partner
Tool and model: codex / gpt-6.2-sol
Plan IDs: CMP-006

## Summary

Prepared the Saudi chart of accounts and VAT data for trading and distribution on the pinned engine. The founder requested G1 preparation while G0 is open. CMP-006 remains `doing` for Tier 3 review.

## Brief

Implement CMP-006 for Saudi trading and distribution SMEs. Deliver a bilingual engine-importable chart, sourced ZATCA VAT codes and reasons, a short accountant review document and tests. Keep the data independent of CMP-021 so CMP-029 can wrap it later. Write no tax calculation logic. Leave `components/` and `contracts/` untouched. Open a Tier 3 PR and leave it unmerged.

## Files touched

- `apps/engine/compliance/ksa/` holds the native chart, number-based company defaults and VAT treatments.
- `apps/engine/change_engine/change_engine/tests/test_cmp_006_ksa_accounts.py` checks the JSON, tree, account types, bilingual labels, defaults and VAT links.
- [Design and sources](../compliance/ksa-coa-and-tax-codes.md) and [open questions](../open-questions.md) record Q-8 and Q-216. PLAN claims CMP-006 for the partner.

## Verification

- CMP-006 unit tests first failed on the missing data, then passed all four checks.
- Pinned engine `v15.124.5` on a fresh synthetic site imported 58 accounts and saved 20 company defaults and four tax templates. Native GL validation accepted account `2170` for an opening entry. The smoke check substituted the chart lookup and called the native Company creation path. The initial bench attempt needed the `Transit` warehouse type from normal site setup. The smoke check seeded it in the rolled-back transaction.
- The full engine suite with a disposable MariaDB 11.4 database passed 184 tests and 61 subtests. One PDF test skipped for lack of a rendering backend. A prior attempt without the disposable database failed to connect for five live tests.
- Docs, plan independence, repository hygiene and secret scan passed.
- Review reconciliation (2026-11-18): added `"status": "draft"`, `"version": "0.1.0"`, and `"review": "unreviewed"` across all three JSON files; replaced paraphrased Z/E reason strings with ZATCA XML Implementation Standard §11.2.4 wording verbatim; documented fail-closed loader behavior, category splitting on `2210` for `CMP-010`, unlinked `1170`/`2150` advances, deferred zakat/EOSB/GOSI/salaries/withholding under `Q-8` (assigned owner `partner`), renumbered `Q-168` -> `Q-216`, and wired `test_cmp_006_ksa_accounts.py` into `.github/workflows/tests.yml`.

## Decisions

- Route ordinary rounding to expense and opening-balance rounding to a balance-sheet account. Use explicit account links for bilingual names that native Company defaults cannot identify by name.
- Make the four tax templates explicit selections and keep customs and reverse-charge mappings available for accountant-reviewed entries. Existing policy applies under ADR-0015, ADR-0031 and ADR-0035.

## Tokens or cost

Unknown.

## Next step

Record line-by-line human review by the founder who did not prompt the change, independent security and cross-model review, and an Arabic-speaking accountant's review. Resolve the chart adoption decision in Q-8 and invoice and posting questions in Q-216 before enabling the data for tenants.
