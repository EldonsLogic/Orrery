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

## Review fix round
Cross-model review (Claude Opus 5.5) of 3cd19b7 asked for changes. Fixed:
- High, false manifest declaration: `manifest.json` now has `touchesLedgerOrTax: true` and `certification.level: tested`, as `zatca_sa` does. `pack.json` `status` is `tested` and `evidenceStatus` stays `unverified`. `SOURCES.md` now says not to promote past `tested` before Arabic sign-off. The earlier "Manifest touchesLedgerOrTax is false" decision above is superseded. Test updated first: it asserts `touchesLedgerOrTax` is true, the level is not above `tested`, and `evidenceStatus` is `unverified`.
- Medium, placeholder ids: `finance.coa_qa_unresolved` and `sales.invoice_print_qa_unresolved` are listed in the manifest `requires`, so the compiler refuses the pack until real components exist. New test asserts both are listed.
- Low, `mandatoryLanguages`: `en` dropped (no source). `SOURCES.md` notes the Arabic requirement is UNVERIFIED for invoices (the source covers financial statements). New test asserts `["ar"]`.
- Eldon Medium 2 (touchesLedgerOrTax false on a rigid pack): resolved by the manifest fix above (`tested` plus `touchesLedgerOrTax: true`, no schema exception needed).
- Eldon Medium 3 (`SOURCES.md` overstated evidence): the e-invoicing row now says only the GTA home page was read, so "VERIFIED" is limited to that page; the KPMG and vatupdate URLs are marked "search excerpt only", and the header no longer claims every URL was accessed as a page.
- Eldon Medium 4: same as the `mandatoryLanguages` fix above (`["ar"]`).
- Eldon Low 6: the traceability test now checks every locked field with a value against a `SOURCES.md` row (field named, and a URL or an explicit "no source" note). It found two gaps, now fixed: the `vatNumberPattern` row said "same as above", and `printFormats.legalLayoutPrecedence` had no row. A new test covers a Ramadan `reducedPeriods` company override (applied, and an end-before-start period refused).
- Eldon Low 5: the CR pattern, week start, timezone and currency stay labelled "UNVERIFIED, no source"; sourcing them is a follow-up (below).
- Eldon High (loader go-live gate): not changed here; the coordinator handles it in a separate PR.
- Tests: 27 pass (23 before, 4 added, 1 renamed and 1 extended).

Next step (follow-ups for the coordinator to turn into plan rows; none added here):
- The loader or registry refuses `draft` packs outside sandbox, and unknown component ids fail closed (today `resolve_country_pack("QA")` returns the placeholders quietly).
- An `invoice` print kind in `pack.schema.json` for countries without VAT (Tier 3, its own PR); then replace the `tax_invoice` stand-in.
- `vatNumberPattern` may be `null` when VAT is unsupported, replacing the `^(?!)$` workaround.
- Source the CR number pattern, week start (`sun`), timezone and currency before the pack leaves `tested`.

## Main merge after CMP-034
Merged `origin/main` (b10fd66, includes CMP-034 #259, the loader go-live gate) with `git merge --no-ff`; no conflicts. Only `components/compliance/country_pack/tests/test_pack_qa.py` changed beyond the merge; no pack data, manifest, evidence, README, loader or schema file was touched.
- Every `load_country_pack` and `resolve_country_pack` call in the test now passes `environment="test"`, because the pack is `tested` with `unverified` evidence and production now refuses it.
- The private-merger calls `apply_company_overrides` became `resolve_country_pack(..., company_overrides=..., environment="test")` (the public resolver).
- New test `test_pack_is_refused_in_production`: with the default environment (and `environment="production"`) both `load_country_pack` and `resolve_country_pack` raise `PackValidationError`.
- Country pack suite: 42 tests pass, including the CMP-034 gate tests from main.
