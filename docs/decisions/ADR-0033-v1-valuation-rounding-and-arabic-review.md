# ADR-0033: v1 stock valuation, rounding and Arabic review defaults

Status: Accepted
Owner: partner
Approved by: both founders. The answers to Q-21, Q-22 and Q-28 were posted on PR #48 on 2026-11-14 at Eldon's instruction. The partner asked for them to be recorded in this session (log `2026-11-14-partner-claude-code-erp-005-close-valuation-rounding.md`).

## Context
The ERP-005 scope work found two places where the pinned engine's defaults disagree with the golden path and the mapping fixture:
- Stock valuation defaults to FIFO, while the golden path assumes Moving Average (Q-21).
- Rounding defaults to "Banker's Rounding (legacy)", while the mapping fixture says `half_up` (Q-22).

See [../specs/core-module-scope-trading.md](../specs/core-module-scope-trading.md) section 5. The Arabic gap audit also raised who reviews Arabic terminology (Q-28; the audit is `docs/specs/arabic-translation-gap-trading.md` in PR #51).

These choices change ledger figures, so they are founder decisions, not engine defaults left in place.

## Decision
1. **Stock valuation (Q-21): Moving Average.**
   - Tenant provisioning sets `Stock Settings.valuation_method = "Moving Average"` explicitly. It must not rely on the engine default.
   - Provisioning sets it before the first stock transaction, because items take their method when stock first moves.
   - A qualified accountant confirms the choice before Phase 2.
2. **Rounding (Q-22): Commercial Rounding, half away from zero.**
   - Tenant provisioning sets `System Settings.rounding_method = "Commercial Rounding"` explicitly.
   - Negative amounts round half away from zero as well, so a credit note mirrors its invoice exactly: an invoice tax of 0.105 rounds to 0.11 and the credit note's -0.105 rounds to -0.11.
   - The mapping fixture's `half_up` means this rule. For positive amounts the two are the same.
   - The rounded-total setting (`Global Defaults.disable_rounded_total`) is a separate, per-market choice and is not decided here.
3. **Arabic review (Q-28).**
   - A native Arabic speaker reviews the Phase 1A invoice.
   - The accountant terminology review (ERP-006 task 4) can wait until Phase 2.
   - One reviewer search covers this and the other accountant reviews (BPL-028, LEG-019, CMP-032).

## Evidence (bench, 2026-11-14, synthetic data only)
The checks ran on a throwaway site created on the pinned bench (Frappe 15.126.0, ERPNext 15.124.5) and dropped afterwards. The setup wizard ran with a synthetic SAR company.

- **Moving Average, set explicitly in Stock Settings.** The item had no method of its own, so it inherited the setting.
  - Received 10 at 100, then 10 at 130: valuation rate 115.
  - Delivered 5: they left at 115, a stock value change of -575. FIFO would have taken them out at 100.
  - Received 5 at 160: rate 126.25, which is (15 × 115 + 5 × 160) / 20.
- **Commercial Rounding.** The engine's `rounded()` sends this method to `_round_away_from_zero` (`frappe/utils/data.py`, lines 1084 to 1085). With the setting on, `flt(x, p)` gives:
  - 2.5 → 3 and -2.5 → -3.
  - 0.125 → 0.13 and -0.125 → -0.13.
  - 1.005 → 1.01 and -1.005 → -1.01.
  - 2.675 → 2.68 and -2.675 → -2.68.
- **Invoice and credit note.**
  - A sales invoice of 0.70 with 15% tax: tax 0.11, grand total 0.81.
  - Its return (credit note): tax -0.11, grand total -0.81. It mirrors the invoice.
- **The legacy default is not symmetric.** Under "Banker's Rounding (legacy)", -2.5 → -2, -0.125 → -0.12, -1.005 → -1.00 and -0.105 → -0.10, while the positive values round up. Credit notes would not mirror invoices under the engine default.

## Alternatives rejected
- **FIFO, the engine default.** The golden path and its expected figures assume Moving Average. FIFO adds layer tracking that owner-led trading companies in scope rarely ask for. The accountant can still reopen this before Phase 2.
- **Leaving rounding at the engine default.** As shown above, it rounds negative halves towards zero, so credit notes would not mirror invoices.
- **"Banker's Rounding" (non-legacy).** Half-to-even differs from the fixture's `half_up` and from how invoices are usually checked by hand.

## Consequences
- Provisioning (ERP-003) must set both settings and verify them after site creation. The ERP-021 and ERP-022 bench runs check them.
- ERP-014 property tests assert Moving Average costs and half-away-from-zero rounding, including credit notes.
- The golden path and the mapping fixture state these rules (BPL-028, BPL-029; PR #53).
- ERP-005's open questions Q-21 and Q-22 are closed, and the row can close.
- Q-25 (MariaDB) is not decided here. The founders will choose after ERP-024 tests a maintained LTS (10.11 or 11.4) on the bench.

## Supersedes
none
