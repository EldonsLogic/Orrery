# Session log: gtm-018-figure-sources

Date: 2026-11-18
Author: partner
Tool and model: claude-code / opus-5.5
Plan IDs: GTM-018

## Summary
Gave every co-founder research figure named in GTM-018 a source and a status: 30 rows in docs/gtm/figure-sources.md, with rules for external use and a not-safe list.

## Files touched
- docs/gtm/figure-sources.md: new. Rules for external use, a list of figures not safe for external use, and source tables for the ERP failure and overrun figures, go-live timelines, the 90% and 75% targets, and the KSA, UAE, Egypt and Qatar leads. It closes with status counts and requests for Eldon's lane.
- docs/gtm/README.md: link to the new file.
- docs/PLAN.md: GTM-018 set to done.
- docs/log/: this file.

## Method
- Grepped docs/ for each figure. The ERP failure rate appears nowhere in docs/ (it is only in the external partner brief), so the file records the usual public forms (Gartner's 2027 prediction, "75% fail", Panorama's overrun figures) to match the brief against.
- Primary sources were read on 2026-11-18. Official PDFs were extracted locally with pdftotext: the ZATCA Security Features and XML Implementation Standards (2023-05-19) and the Detailed Technical Guidelines v2, UAE Cabinet Decision 116 of 2022, the FTA e-invoicing programme PDF (30 June 2026), and Panorama's 2017 ERP report. Official web pages read: MoF tax page, ETA eInvoicing SDK pages, GTA taxes page.
- Could not fetch: the Gartner pages (HTTP 403), the ETA e-invoicing page (404), the official Qatar Cabinet text (not found). These are recorded as such; no quote was invented.

## Results
- VERIFIED 13, SECONDARY 3, FOUNDERS' TARGET / HYPOTHESIS 7, UNVERIFIED 7.
- Corrections: "75% of ERP projects fail" has no primary source. Gartner's 70% figure is a 2027 prediction about business-case goals, not a failure rate. Panorama's 74% counts budget overruns (2017 survey, 342 respondents). UAE corporate tax is 9% only above AED 375,000. The Egypt "unified chart of accounts" lead is unsourced and is probably the unified GS1/EGS item codes.

## Decisions
- None. The file applies existing rules (RULES 12, ADR-0017) and does not set new ones.

## Tokens or cost
Unknown.

## Next step
- Eldon's lane: the 10 requests at the end of docs/gtm/figure-sources.md (country-matrix, 03-regulations, 02-market-and-customer, 08 table labels).
- Partner: check the external partner brief against figure-sources.md before it goes anywhere. Someone with Gartner access should record the exact Gartner quote (row A-3).
- CMP-021 (Egypt compliance research) can pick up E-3 and E-4.
