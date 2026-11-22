# Session log: cmp-028-egypt-country-pack

Date: 2026-11-21
Author: partner
Tool and model: antigravity / gemini-4-hydrogen
Plan IDs: CMP-028

## Summary
Added the draft Egypt country pack (`country.eg` `0.1.0`) under `components/compliance/country_pack/packs/eg/0.1.0/`, its sourced research notes, unreviewed Arabic strings table, component manifest, and `test_pack_eg.py` unit tests.

## Files touched
- `components/compliance/country_pack/packs/eg/0.1.0/pack.json`: draft Egypt country pack (`status: draft`, `evidenceStatus: unverified`, `testOnly: false`), declarative metadata only (no tax or e-invoice maths), `payrollHooks` disabled/null for out-of-scope v1 payroll/social insurance, `Africa/Cairo` timezone, Gregorian calendar, Sun-Thu week, `EGP` currency, `western` default digits, and fail-closed `overridesPolicy`.
- `components/compliance/country_pack/packs/eg/0.1.0/manifest.json`: component manifest (`country.eg` `0.1.0`, `kind: rigid`, `certification.level: tested`, `touchesLedgerOrTax: true`, `reviewedBy: []`, `owner.github: sayegh9`).
- `components/compliance/country_pack/packs/eg/0.1.0/strings.json`: unreviewed Arabic label registry (`reviewStatus: proposed_for_native_speaker_review`, ADR-0033).
- `components/compliance/country_pack/packs/eg/0.1.0/README.md`: full facts, URLs, access dates (`2026-11-18`), and confidence labels from `docs/compliance/egypt-research.md`, `docs/compliance/country-matrix.md`, and `docs/architecture/calendars-and-locale.md`, plus the unreviewed Arabic labels list.
- `components/compliance/country_pack/tests/test_pack_eg.py`: unit tests loading `EG` via `load_country_pack`, validating `pack.json` and `manifest.json`, verifying DST behavior on `Africa/Cairo`, verifying disabled v1 payroll hooks and unreviewed Arabic markers, testing locked-path override rejection, and verifying valid company overrides.

## Decisions
- Followed [ADR-0015](../decisions/ADR-0015-country-packs-calendars-locale.md), [ADR-0024](../decisions/ADR-0024-four-phase-1-markets.md), [ADR-0031](../decisions/ADR-0031-rigid-zone-code-authorship.md), and [ADR-0033](../decisions/ADR-0033-v1-valuation-rounding-and-arabic-review.md).
- Left `docs/PLAN.md`, `pack.schema.json`, `loader.py`, `contracts/`, `.github/`, and `packs/README.md` untouched (PR #251 already claims `CMP-028` in `docs/PLAN.md`).
- Kept `pack.json` strictly within `pack.schema.json` (`eInvoicing.mode: eg_e_invoice`, `vatSupported: true`, `taxCodesRef` string ref with no inline tax maths); documented the full statutory sources, UNVERIFIED items, and POS e-receipt G2 scope note in `README.md`.

## Prompt and brief (ADR-0031)
- Task: Implement plan row `CMP-028` ("Egypt country pack") for the partner founder (`sayegh9`), Tier 3 rigid-zone compliance data. Deliver `packs/eg/0.1.0/pack.json` and `manifest.json` (`status`/`evidenceStatus` draft/UNVERIFIED where schema allows, `testOnly: false`), source every statutory fact from `docs/compliance/egypt-research.md` (with URL and access date) or mark UNVERIFIED, keep v1 payroll/social insurance null/disabled, mark Arabic labels unreviewed (ADR-0033), include no tax or e-invoice maths (principle 3), and add `test_pack_eg.py` checking `load_country_pack`, locked overrides, and valid overrides.

## UNVERIFIED and unreviewed items
- **VERIFIED**: ETA eInvoicing/eReceipt SDK API existence, registration flow, CAdES-BES SHA-256 UTF-8 signing spec, and PreProd/Prod environments (`https://sdk.invoicing.eta.gov.eg/`, accessed `2026-11-18`).
- **UNVERIFIED** (secondary, snippets, conflicting, or research needed): VAT 14% / 5% machinery / schedule tax / EGP 500,000 threshold / monthly filing / Law 157 of 2025 / Law 149 of 2026; ETA mandate rollout dates, 2026 decree, HSM/USB token rules, e-receipt thresholds (50k/150k EGP) and POS G2 scope; 5-year archive retention; VAT/CR number patterns; unified CoA template ref; `half_away_from_zero` statutory VAT rounding; `Africa/Cairo` 2023 DST rule; Gregorian primary calendar / Hijri announcements / Coptic out of v1; Sun-Thu work week & hours; Jan 1 fiscal year default; public holidays; `western` digit system default; `EGP` currency & FX rules; mandatory Arabic invoice language; disabled payroll/social insurance research notes (Law 148/2019, Law 7/2024, Law 14/2025).
- **Unreviewed Arabic labels (ADR-0033)**: `حزمة دولة مصر` (`name.ar`), `مصلحة الضرائب المصرية` (`country.eg.authority.ar`).

## Tokens or cost
Unknown.

## Next step
- Merge PR #251 (`CMP-028` row claim in `docs/PLAN.md`), complete Tier 3 human line-by-line review + cross-model review (`ADR-0031`, `ADR-0035`), obtain native Arabic review (`ADR-0033`), and obtain Egyptian counsel/accountant sign-off on all `UNVERIFIED` items before promoting `country.eg` above `draft`/`unverified`.

## Review fix round
Addressed findings from the Opus 5.5 cross-model review and Eldon's Fable 5.2 review of `0ade5e2` on PR #256:
- `components/compliance/country_pack/packs/eg/0.1.0/pack.json`: aligned `status` with `manifest.json` `certification.level` at `tested` while keeping `evidenceStatus: unverified`; changed `printFormats.mandatoryLanguages` from `["ar", "en"]` to `["ar"]` (language rules were not researched).
- `components/compliance/country_pack/packs/eg/0.1.0/manifest.json`: listed `finance.coa_eg` and `compliance.eta_eg` in `requires`; removed the three nonexistent `print_format` artifacts from `provides` (leaving `compliance.eta_eg` as owner of those print formats and pointing `compliance.country_pack.eg` at `loader.load_country_pack` and `loader.resolve_country_pack`).
- `components/compliance/country_pack/packs/eg/0.1.0/README.md`: moved `required`, `mode`, and `componentId` out of the `VERIFIED` SDK row into the `UNVERIFIED` mandate row; marked "July 1 can override" explicitly `UNVERIFIED`; added ETA e-invoicing spec decimal precision as an explicit research gap in the rounding row; recorded open counsel question Q11 (`mandatoryLanguages: ["ar"]`).
- `components/compliance/country_pack/tests/test_pack_eg.py`: updated tests first — asserted `pack.status == manifest.certification.level == "tested"` and `evidenceStatus == "unverified"`, asserted every component id referenced by `pack.json` is listed in `manifest.requires` and `provides` lists no `print_format` artifacts, replaced the vacuous `rate`/`rates` assertions with a `taxCodesRef` and `mandatoryLanguages` check, and replaced `hijri_umm_al_qura` in the override test with `"gregorian"`.

## Main merge after CMP-034
Merged `origin/main` (b10fd66, includes CMP-034 #259, the loader go-live gate) with `git merge --no-ff`; no conflicts. Only `components/compliance/country_pack/tests/test_pack_eg.py` changed beyond the merge; no pack data, manifest, evidence, README, loader or schema file was touched.
- Every `load_country_pack` and `resolve_country_pack` call in the test now passes `environment="test"`, because the pack is `tested` with `unverified` evidence and production now refuses it.
- The private-merger calls `apply_company_overrides` became `resolve_country_pack(..., company_overrides=..., environment="test")` (the public resolver).
- New test `test_pack_is_refused_in_production`: with the default environment (and `environment="production"`) both `load_country_pack` and `resolve_country_pack` raise `PackValidationError`.
- Country pack suite: 30 tests pass, including the CMP-034 gate tests from main.
