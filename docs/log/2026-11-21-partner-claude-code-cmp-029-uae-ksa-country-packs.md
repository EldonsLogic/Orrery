# Session log: cmp-029-uae-ksa-country-packs

Date: 2026-11-21
Author: partner
Tool and model: claude-code (Claude Opus 5.5), implementation sub-agent
Plan IDs: CMP-029

## Summary
Added the first real country packs, KSA and UAE 0.1.0, under the packs root `components/compliance/country_pack/packs/`, built on the CMP-021 framework. Both are `status: draft`, `evidenceStatus: unverified`, `testOnly: false`. They hold declarative metadata only (no tax, ledger or e-invoice maths, ADR-0031; Tier 3). The KSA pack references the CMP-006 chart and VAT treatments by path and version range and copies nothing. Payroll and WPS are off in both (v1 scope; CMP-015 is G3). No loader, schema, contract, PLAN or CI file was changed.

## Files touched
- components/compliance/country_pack/packs/README.md: states the packs root and layout
- components/compliance/country_pack/packs/sa/0.1.0/{pack,manifest,evidence}.json: KSA pack, component manifest, per-fact evidence
- components/compliance/country_pack/packs/ae/0.1.0/{pack,manifest,evidence}.json: UAE pack, component manifest, per-fact evidence
- components/compliance/country_pack/tests/test_pack_sa_ae.py: 21 tests (load from the real root, locked areas against overrides, testOnly still refused, valid company overrides, no maths, payroll off, CMP-006 refs, manifests against the contract, evidence coverage, Arabic labels unreviewed)

## Decisions
- Per-fact sources go in a sibling `evidence.json`: `pack.schema.json` has no per-fact evidence field and caps `notes` at 500 characters. The schema was not changed. A test requires every leaf of the evidenced areas to have an entry, each sourced label to have a URL and access date, and anything else to be UNVERIFIED or PLATFORM-DEFAULT with a reference. Proposal for a later row: add an optional `sources` array to the pack schema.
- Manifest `certification.level` is `tested`, not `draft`: the manifest contract forbids `draft` when `touchesLedgerOrTax` is true. The pack status stays `draft`.
- UAE `eInvoicing.required` is false in 0.1.0: no go-live date has passed (AED 50m+ by 2027-01-01). A later pack version sets it true when CMP-011 exists.
- Unresolved references are listed in `pendingRefs`: KSA chart component id and `sa.holidays`; UAE chart (`pending:`), tax invoice mode (Q-553), `compliance.pint_ae` placeholder id and `ae.holidays`. The UAE has no tax codes (`taxCodesRef: null`).
- No source was re-read in this session; access dates are those recorded in country-matrix.md, ksa-coa-and-tax-codes.md and uae-einvoicing-provider-selection.md.

## Tokens or cost
Unknown.

## Next step
Tier 3 line-by-line review by a different model and the other founder. Native Arabic review of the three Arabic strings (two pack names, also used in the manifests, and the Ramadan hours label; ADR-0033). Open rows needed for a UAE chart of accounts and UAE tax codes; CMP-024 holiday calendars; a pack schema `sources` field.

## Review fix round
Fixes the five findings of the cross-model review (Gemini 4 Hydrogen) of a39a593 on PR #257. Merged origin/main first (no conflicts). Tests were written first and failed, then the data was fixed. The suite now has 32 tests and all pass.
- High: each manifest's `requires` now lists every component id its pack references, including ones that do not exist yet, so the compiler fails closed. UAE: `finance.coa_ae_trading`, `compliance.pint_ae` and `ae.holidays`. KSA: `finance.coa_sa_trading`, `compliance.zatca_sa` and `sa.holidays`. The chart and holiday ranges are `>=0.1.0 <0.2.0`, matching the pack. New test: the set of referenced ids (every `componentId` leaf, `holidays.calendarRef.id` and the print template components) equals the set in `requires`. Note: `ae.holidays` and `sa.holidays` match the id pattern but not the documented area list (core, compliance, ...). CMP-024 should settle the calendar id.
- Medium: pack `status` is now `tested`, which matches `certification.level`. `evidenceStatus` stays `unverified` and `reviewedBy` stays `[]`. The notes and manifest descriptions no longer say "draft". The status test now asserts that the status equals the level, `touchesLedgerOrTax` is true, `reviewedBy` is empty and `evidenceStatus` is `unverified`.
- Low: the UAE `tax.crNumberPattern` fact is UNVERIFIED with no ref and no sources. The country matrix says nothing about trade-licence formats. A test pins this.
- Low: the manifests' `tests[0].path` is now repo-root relative, as in packs/qa and packs/eg. The test resolves it from the repo root and rejects `.` or `/` prefixes.
- Low: packs/README.md describes test modules generically (`test_pack_<cc>.py` or similar). A test checks this.

## Fix round 2 (Eldon)
Fixes Eldon's cross-model review (Fable 5.2) of a39a593 on PR #257, checked against f4cd70b. Merged origin/main first (no conflicts). Tests were written first and failed (11 failures, 5 errors), then the data was fixed; the pack suite now passes (44 tests in the country pack folder). Session date 2026-11-22.

Already fixed in round 1 (f4cd70b): item 2 in part (the chart requirement was listed) and item 11 (status equals the manifest level, asserted).

Fixed now:
1. KSA ZATCA Phase 2: a new `goLiveBlockers` list in `evidence.json` holds `zatca_phase2` (K3, Wave 25, VERIFIED-OFFICIAL), and the manifest requires the unresolvable capability `compliance.zatca_sa.phase2_clearance_reporting`. No reporting window is stated. Q-559 asks whether the pack or the Blueprint decides the mode, linking ADR-0042.
2. KSA manifest: the `compliance.zatca_sa` range is now `>=0.1.0 <0.2.0`; the tax codes are required as the placeholder `finance.vat_sa_treatments`.
3. KSA templates now name the placeholder `documents.zatca_sa_layouts` (owner ERP-016, `branded_documents.py`), listed in `requires` and `pendingRefs`.
4. The KSA e-invoicing entry is split: required and authority (K1, VERIFIED-OFFICIAL); mode and componentId are separate PLATFORM-DEFAULT design choices.
5. KSA cites Q-267 (tax codes) and records Q-23 and Q-555 as the `immutable_ledger` go-live blocker.
6. UAE e-invoicing: the `uae_e_invoicing` blocker (AED 50m+ by 2027-01-01, VERIFIED-OFFICIAL) requires `compliance.pint_ae`, now also `eInvoicing.componentId`. `required` stays false (the date has not passed); no threshold is computed. The tax codes are `pending:ae_vat_treatments`, required as `finance.vat_ae_treatments`. New test: while any pending ref or blocker exists, neither the pack status nor the manifest level may be above `tested`.
7. UAE `authority` is now UNVERIFIED, split from the mode fact.
8. UAE mode is the Blueprint value `uae_e_invoicing` (the pack schema pattern allows it); a test checks both modes against the Blueprint enum.
9. UAE cites Q-210, Q-211 and Q-213 (blocker); retention cites Q-213; the language entry cites U7.
10. `printFormats.mandatoryLanguages` is `["ar"]` in both. KSA: K7 (SECONDARY). UAE: no source (U7), UNVERIFIED, Arabic kept as the minimal list the schema needs.
12. The rate test now rejects digits in locked strings unless the path is a known id format (semver, version range, HH:MM, anchored id pattern, Blueprint mode), and retention outside 1 to 10 years. A mutation test proves `vat:0.15`, `standard_15_pct` and a 15-year retention fail.
13. Sources marked "not fetched" or "not read" no longer carry access dates (a test enforces it); both retention numbers stay locked and UNVERIFIED with a note.

Stopped:
14. The duplicate loader function stays: the manifest contract needs at least one `provides` artifact, and no artifact type fits pack data. A test pins the single shared ref. `country-pack-framework.md` was not edited (a later convention PR documents `evidence.json`).

New open question: Q-559 (number assigned by the coordinator; Q-558 and Q-560 belong to #260 and #259).

## Main merge after CMP-034
Merged `origin/main` (b10fd66, includes CMP-034 #259, the loader go-live gate) with `git merge --no-ff`. One conflict, in `docs/open-questions.md`: kept both rows, Q-559 (this PR) then Q-560 (from main); no row dropped or duplicated. `docs/PLAN.md` merged without conflict. Only `components/compliance/country_pack/tests/test_pack_sa_ae.py` changed beyond the merge; no pack data, manifest, evidence, README, loader or schema file was touched.
- Every `load_country_pack` and `resolve_country_pack` call in the test now passes `environment="test"`, because both packs are `tested` with `unverified` evidence and production now refuses them.
- The private-merger calls `apply_company_overrides` became `resolve_country_pack(..., company_overrides=..., environment="test")` (the public resolver).
- New test `test_real_packs_are_refused_in_production`: for SA and AE, with the default environment (and `environment="production"`), both `load_country_pack` and `resolve_country_pack` raise `PackValidationError`.
- Country pack suite: 59 tests pass, including the CMP-034 gate tests from main.
