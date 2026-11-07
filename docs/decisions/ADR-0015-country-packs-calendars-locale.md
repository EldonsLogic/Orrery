# ADR-0015: Country packs, calendars and locale

Status: Accepted
Owner: eldon
Approved by: Eldon and partner

## Context
Founder requirement: operate in KSA, UAE and Egypt, with per-company calendar and week settings. Launch order stays KSA first, UAE second, Egypt third. Egypt regulations (e-invoicing, VAT, data protection, payroll) are all UNVERIFIED and need research (GTM-017). Commerce and tax are Gregorian in practice in all three countries (UNVERIFIED). Hijri matters for Saudi official and some contract contexts, possibly the zakat year, and religious dates in all three. Egypt may also use the Coptic calendar in some contexts (UNVERIFIED).

## Decision
1. Operating countries: KSA, UAE, Egypt.
2. A Country Pack is a certified rigid-zone component bundle per country: tax, e-invoicing, holiday calendar, default weekend and work-week, payroll rules, document templates, languages, number and currency formats. Packs are versioned components under the manifest contract; AI never edits them.
3. The Blueprint company profile selects the pack. A company may override only the settings the pack marks as overridable.
4. Dates are stored canonically as Gregorian (ISO, UTC). Hijri (Umm al-Qura) is a display, entry and rule layer only; it is never the stored value.
5. Per-company settings, defaulted from the pack: week start day, weekend days, working days and hours (including reduced Ramadan hours), timezone, primary and secondary display calendar (Gregorian or Hijri), fiscal year type and start, holiday calendar with admin-editable moon-sighting overrides, number system (Western or Arabic-Indic digits).
6. Legally required document dates and layouts follow the pack and win over company settings (see ADR-0014 for the same rule on branding).

## Alternatives rejected
- Hard-code KSA rules and fork per country: violates ADR-0008.
- Store Hijri dates: conversion ambiguity (moon sighting) corrupts data.
- One global weekend setting: Saudi, UAE and Egypt work-weeks differ and change over time.

## Consequences
- Needs a conversion library choice with tests, per-company settings, holiday overrides, dual-date documents and date pickers in both calendars (see plan items CMP-021 onward).
- Egypt pack is blocked on research; do not claim Egypt compliance until verified.
- Timezone and Egypt daylight-saving behaviour must be verified (UNVERIFIED).
- Complexity risk recorded as R-031.

## Supersedes
none
