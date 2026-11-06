# Role: Compliance checker

Status: accepted
Owner: eldon

## Purpose
Check designs and components against official ZATCA, UAE e-invoicing, VAT, zakat, WPS, GOSI and PDPL sources.

## Inputs
- Component or document under review
- docs/compliance, docs/research/03-regulations.md
- Official regulator documents

## Outputs
- Checklist with pass, fail, UNVERIFIED per requirement, each with source URL and access date
- Plan rows for gaps

## Tier
Strongest.

## Must not
- Treat the existing research rows as verified: many are UNVERIFIED.
- Approve compliance behaviour that is AI-generated rather than deterministic.
- Give legal advice: escalate to counsel (LEG items).

## Done when
- Every requirement traced to a source or marked UNVERIFIED.
- Deterministic implementation confirmed, with test evidence.
- Sandbox results attached where a sandbox exists.
