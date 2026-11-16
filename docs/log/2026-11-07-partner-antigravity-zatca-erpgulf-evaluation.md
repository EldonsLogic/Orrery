# Session log: zatca-erpgulf-evaluation

Date: 2026-11-07
Author: partner
Tool and model: antigravity
Plan IDs: CMP-002

## Summary
Evaluated the ERPGulf ZATCA e-invoicing app (v3.0.1, commit 7d686f7) across licence, Phase 2 coverage, and maintenance health, recommending adopting its pure Python cryptographic and UBL logic while wrapping it to enforce engine invisibility, transactional hash chaining, and CI sandbox testing.

## Files touched
- docs/compliance/zatca-erpgulf-evaluation.md: Technical evaluation report covering MIT licence verification, Phase 2 UBL/XAdES/QR implementation audit, concurrency risks on PIH hash chaining, code quality, and implementation roadmap.
- docs/compliance/e-invoicing.md: Cross-linked evaluation report in ZATCA section.
- docs/legal/licence-register.md: Updated ERPGulf upstream repo URL, pinned evaluated version v3.0.1, and recorded status.
- docs/risks.md: Updated risk R-018 to mitigating with partner ownership and evaluation findings.
- docs/PLAN.md: Marked CMP-002 as done.
- docs/STATUS.md: Regenerated via build_status.py.

## Decisions
- Adopt ERPGulf's pure Python cryptographic and XML generation modules for G1 ZATCA Phase 1 & 2 compliance (avoids Java/CLI external binaries and AGPL copyleft contamination).
- Do not run upstream ERPGulf unmanaged in production; vendor/fork core logic to strip Desk UI and GIFs (ADR-0016 engine invisibility) and replace `Company.custom_pih` with transactional row-level locked hash chaining.

## Tokens or cost
Approx. 25k tokens across Gemini model calls and GitHub REST API inspections.

## Next step
Proceed to CMP-003 (ZATCA Phase 1 invoice generation with QR and mandatory fields) and CMP-004 (ZATCA Phase 2 sandbox clearance and reporting).
