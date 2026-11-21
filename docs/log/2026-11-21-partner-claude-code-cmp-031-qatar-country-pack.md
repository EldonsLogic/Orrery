# Session log: cmp-031-qatar-country-pack

Date: 2026-11-21
Author: partner
Tool and model: claude-code (Sonnet 5.5)
Plan IDs: CMP-031

## Summary
Added the Qatar country pack 0.1.0 (draft, evidence UNVERIFIED) from the CMP-030 research: no VAT in force, no e-invoicing law enacted, payroll and WPS disabled, Gregorian fiscal year, Arabic text unreviewed. It loads through the existing loader, with 14 new tests. Tier 3 (rigid-zone compliance data, ADR-0031).

## Files touched
- components/compliance/country_pack/packs/qa/0.1.0/pack.json: the pack
- components/compliance/country_pack/packs/qa/0.1.0/manifest.json: companion manifest, level draft
- components/compliance/country_pack/packs/qa/0.1.0/SOURCES.md: every value with source URL, access date and evidence status
- components/compliance/country_pack/tests/test_pack_qa.py: load, locked-versus-override and override validation tests

## Decisions
- None. Schema gaps found, not worked around by editing the schema (open for the founders):
  - `coaTemplate` and `printFormats.templates` need component refs, but no Qatar chart or print component exists: unresolved placeholder ids are used.
  - The print `kind` enum has no invoice without tax; `tax_invoice` is a stand-in.
  - No way to express an empty, effective-dated VAT slot (research proposal): `taxCodesRef` is null.
  - `vatNumberPattern` is required: `^(?!)$` (matches nothing) says no VAT number exists.
  - `qa.holidays` calendar ref points to a calendar that does not exist yet.
  - Manifest `touchesLedgerOrTax` is false because the schema forbids level draft when true.

## Tokens or cost
Unknown.

## Next step
Native Arabic review of the three Arabic labels (ADR-0033). Re-check VAT and e-invoicing status against official sources. Author a Qatar chart of accounts, invoice template and `qa.holidays` calendar (new plan rows if wanted).
