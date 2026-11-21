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
