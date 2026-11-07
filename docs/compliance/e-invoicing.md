# E-invoicing (ZATCA and UAE)

Status: draft
Owner: eldon

Only what [../research/03-regulations.md](../research/03-regulations.md) supports (access date 2026-11-04). Everything else is UNVERIFIED or research needed. Rows reference [country-matrix.md](country-matrix.md).

## KSA: ZATCA
| Topic | What the research supports | Product implication |
|---|---|---|
| Phase 1 (generation) | In force 2021-12-04; structured e-invoices, no edit/delete after issue, sequential numbering, archive, QR on simplified invoices (K1, VERIFIED-OFFICIAL) | Invoice component issues immutable documents; corrections only by credit/debit note |
| Phase 2 (integration) | Enforceable from 2023-01-01 in waves; Fatoora connection, clearance and reporting, UBL 2.1 XML, cryptographic stamp, CSID onboarding, hash chain (PIH/ICV), UUID (K2). Clearance/24h reporting semantics UNVERIFIED | Compliance app (ERPGulf, MIT; spike-gated) plus our wrapper; retries and offline queue; error surfacing in the chat |
| Waves | Wave 25 published 2026-07-24: revenue > SAR 187,500, integrate by 2027-02-01; later waves given >= 6 months' notice (K3) | Wave and date are tenant settings; readiness check at sign-up; no hard-coded wave logic |
| Vendor obligations | Pass SDK validation and sandbox tests; per-unit CSID and keys; directory listing reportedly optional (K4, SECONDARY) | Test plan below; key custody in [../security/threat-model.md](../security/threat-model.md) T10 |
| Arabic | Arabic details required on tax invoices, may be bilingual (K7, SECONDARY) | Bilingual templates; Arabic fields stored separately |
| Hijri | No requirement found (K8) | Gregorian canonical; Hijri display later if confirmed |
| Retention | UNVERIFIED (K9) | Immutable archive of signed XML + PDF/A; configurable period |

Licence rule: use the MIT ERPGulf app, not the AGPL app ([../product/FRAPPE-BUILD-GUIDE.md](../product/FRAPPE-BUILD-GUIDE.md)). Detailed technical evaluation of ERPGulf completed in [zatca-erpgulf-evaluation.md](zatca-erpgulf-evaluation.md) (CMP-002).

### ZATCA sandbox testing plan
| Step | Check | Evidence |
|---|---|---|
| 1 | Read developer portal manual and technical guideline (not read in research); list exact test scenarios | Notes in research file (research needed) |
| 2 | Onboard a test EGS unit in the sandbox (OTP, CSR, compliance CSID, production CSID) | Log of calls |
| 3 | Issue standard (B2B) and simplified (B2C) invoices, credit and debit notes in sandbox; run ZATCA SDK validator on every XML | Validator output stored |
| 4 | Verify QR (TLV), hash chain (PIH/ICV), UUID, stamp | Test report |
| 5 | Arabic and bilingual PDF review: RTL shaping, mandatory Arabic fields, QR clear zone | Screenshots reviewed by an Arabic speaker |
| 6 | Failure paths: rejection, timeout, duplicate, offline queue replay | Test cases |
| 7 | Rerun on every ERPGulf app or ZATCA spec update (regulation-watch trigger) | CI job against sandbox where possible |
| 8 | Tax adviser reviews sample invoices | Sign-off recorded |
Gate: G1 requires a ZATCA invoice to pass the sandbox ([../GATES.md](../GATES.md)). Nothing goes to production for a tenant until the tenant's own onboarding passes.

## UAE
| Topic | What the research supports | Product implication |
|---|---|---|
| Legal base | Ministerial Decisions 243 and 244 of 2025; MD 66 of 2026 amends MD 244 (U1, SECONDARY; PDFs not parsed) | Verify on MoF/FTA before customer claims |
| Model | Peppol-based 5-corner via accredited service providers (ASP); PINT-AE (U3, UNVERIFIED) | Generate PINT-AE XML, send via ASP API, receive inbound; no own Peppol AP in v1 |
| Dates | Revenue < AED 50m: appoint ASP by 2027-03-31, go-live 2027-07-01; >= AED 50m: 2027-01-01; sources conflict (U2) | UAE is second market; July 2027 is the opening; do not publish dates until confirmed |
| Accredited provider partner | Official ASP list not found (U4) | Shortlist 1-2 ASPs; evaluate API, price (provider fees UNVERIFIED), Arabic support, liability split; counsel question 2 |
| Format and fields | Tax invoice fields (U6, UNVERIFIED current) | Validate before submission |

### UAE partner selection checklist
Accreditation status verified on official list; API and sandbox; PINT-AE support; inbound handling; pricing model; data location; DPA; SLA and support; exit path; liability. All research needed.

## Common design rules
- Dates, thresholds and rates in effective-dated config tables ([../research/03-regulations.md](../research/03-regulations.md) section 3).
- Signed XML and rendered PDF archived immutably, retention configurable by country.
- Deterministic code only; AI never edits e-invoicing logic.
- Rejections become plain messages in the brand voice with the exact field ([../product/app-screens.md](../product/app-screens.md)).
