# Session log: cmp-037-review-followups

Date: 2026-11-23
Author: eldon
Tool and model: claude-code
Plan IDs: CMP-037

## Summary
Fixed the four findings from sayegh9's post-merge review of PR #290 in the CMP-037 research doc, and added sourced corrections for the earlier log.

## Files touched
- docs/research/cmp-037-official-sources.md: Qatar "no VAT" and "no e-invoicing spec" now "not found; UNVERIFIED"; ETA HTML references reclassed as documentation pending executable artifacts (not machine-readable); Wave 24 deadline marked UNVERIFIED (no source URL identified).
- docs/log/2026-11-23-eldon-claude-code-cmp-037-review-followups.md: this log.

## Sourced corrections to the CMP-037 log
The earlier log (`2026-11-23-eldon-claude-code-cmp-037-official-sources.md`, append-only) repeats claims without URL or access date. Sources, confirmed in sayegh9's review of 2026-11-23 and the same pages as in the research doc:
- ZATCA XML Implementation Standard v1.2 (2023-05-19), section 10, p.29, half-up rounding: https://zatca.gov.sa/ar/E-Invoicing/SystemsDevelopers/Documents/20230519_ZATCA_Electronic_Invoice_XML_Implementation_Standard_%20vF.pdf (accessed 2026-11-23). Whether it makes `tax.roundingRule` statutory stays with the accountant (Q-601).
- UAE MD 197 of 2026 (amends MD 243), MD 168 of 2026, CD 173 of 2026 on the MoF e-invoicing page: https://mof.gov.ae/en/about-us/initiatives/einvoicing/ (accessed 2026-11-23). None is named in the AE pack `evidence.json`.
- SA VAT filing, monthly above SAR 40m annual supplies, quarterly at or below: https://zatca.gov.sa/en/MediaCenter/News/Pages/Submit-VAT-Return-for-Oct-andQ3-2026.aspx (accessed 2026-11-23). Still a lead for `tax.filingPeriods`, UNVERIFIED until the accountant signs off.
- QA Minister of Labour Decision 50 of 2026 (WPS): SECONDARY, https://taxnews.ey.com/news/2026-2050-qatar-amends-wage-protection-system-salary-payment-deadlines-effective-8-september-2026 (not opened). UNVERIFIED.
- Sites that blocked automated fetch (sandbox.zatca.gov.sa, laws.boe.gov.sa, gosi.gov.sa, uaelegislation.gov.ae, mohre.gov.ae, almeezan.qa): see the research doc, BLOCKED rows, accessed 2026-11-23.

## Decisions
- None.

## Tokens or cost
Unknown.

## Next step
Packs lane (CMP-036, Q-601, AE evidence, SA filing periods) uses the confirmed items. Wave 24 source still to be found.
