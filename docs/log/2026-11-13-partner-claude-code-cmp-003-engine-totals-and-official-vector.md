# Session log: cmp-003-engine-totals-and-official-vector

Date: 2026-11-13
Author: partner
Tool and model: claude-code / opus-5.5
Plan IDs: CMP-003

## Summary
Reworked the ZATCA Phase 1 component to the conditions of proposed ADR-0031: a real ZATCA test vector, no tax computed in our code, and no claims of review, certification or engine testing that have not happened.

## Files touched
- components/compliance/zatca_sa/phase1.py: removed the VAT and total computation (`compute_totals`, line amount properties, the hard-coded 15 percent rate and rounding). The invoice now takes the totals the engine computed (`totals`), checks they are non-negative, already rounded to 2 decimals and add up (fail closed, never corrected), and validates before generating the QR. Quantities are no longer rounded; negative quantities and non-finite amounts (NaN, Infinity) are rejected with a validation error. A line needs a VAT rate from the engine; category S needs a rate above zero, and the exact rate belongs to the country pack.
- components/compliance/zatca_sa/tests/test_phase1.py: the "official" vector is now the ZATCA published example (E-invoicing Detailed Technical Guideline, section 6.4, https://zatca.gov.sa/en/E-Invoicing/Introduction/Guidelines/Documents/E-invoicing-Detailed-Technical-Guideline.pdf, accessed 2026-11-13; checked against the PDF). It replaces a "Bob's Dogs" vector that was the code's own output. Added tests: document-discount VAT taken from the engine, missing totals, inconsistent totals, unrounded totals, missing VAT rate.
- apps/engine/change_engine/change_engine/tests/test_zatca_phase1_engine.py: passes engine totals.
- components/compliance/zatca_sa/manifest.json, __init__.py, components/README.md: removed "certified"; `reviewedBy` is empty until a named human review. The schema forces level `reviewed` on any tax component and has no pre-review state, so `reviewed` with nobody named is the only valid value today; this is not a claim of review (raised as Q-19 in PR #48); `testedAgainst` is empty (not run on a bench); `rtlVerified` false.

## Decisions
- Follows proposed ADR-0031 (PR #48). Defects removed with the computation: VAT ignored the document discount (100.00 less 10.00 gave VAT 15.00, not 13.50), and VAT was summed from rounded lines where ZATCA rounds once at document level (Electronic Invoice XML Implementation Standard, chapter 10).
- Not changed, flagged for review: the QR timestamp appends "Z" to the local issue time without converting to UTC (ERPGulf does the same); and the ERPGulf encoder (`create_qr.py`, MIT) was compared but not adopted, since ours now matches the official vector.

## Tokens or cost
Unknown.

## Next step
Eldon (who did not prompt this code) reviews it line by line and is added to `reviewedBy`; ADR-0031 accepted; then merge after #42. The accountant reviews before any real data. CMP-004 (sandbox) proves conformance.
