# Country compliance matrix

Status: draft
Owner: eldon

Source: [../research/03-regulations.md](../research/03-regulations.md) (prepared 2026-11-04; all source access dates 2026-11-04). NOT legal advice. Evidence labels from the research: VERIFIED-OFFICIAL, SECONDARY (treat as UNVERIFIED), UNVERIFIED. Rows below keep the research ID. "Status" = our evidence state, not our implementation state (implementation tracked in [../PLAN.md](../PLAN.md)). Many official PDFs could not be parsed in the research.

## KSA
| ID | Area | Requirement (short) | Source (accessed 2026-11-04) | Effect on product | v1 must-have | Status |
|---|---|---|---|---|---|---|
| K1 | E-invoicing Phase 1 | Generate/store e-invoices with compliant software; QR on simplified invoices; in force 2021-12-04 | https://zatca.gov.sa/en/E-Invoicing/Introduction/Pages/Roll-out-phases.aspx | Structured invoices, no edit/delete after issue (credit/debit notes), sequential numbers, archive, QR (TLV) | Yes | VERIFIED-OFFICIAL |
| K2 | E-invoicing Phase 2 | Integration with Fatoora: clearance (B2B), reporting within 24h (B2C) [24h semantics UNVERIFIED], UBL 2.1, stamp, CSID, hash chain, UUID; enforceable from 2023-01-01 in waves | same page; technical docs listed in research row K2 (not read) | Full XML, signing, QR, hash chain, onboarding, API client with retries/offline queue | Yes | Wave mechanics VERIFIED-OFFICIAL; details UNVERIFIED |
| K3 | Wave status | Wave 25 published 2026-07-24: revenue > SAR 187,500 in any of 2022-2025; integrate by 2027-02-01; later waves notified >= 6 months ahead. Wave 24 (> SAR 375,000, by 2026-06-30) snippet only | https://zatca.gov.sa/en/MediaCenter/News/Pages/Wave25-E-invoicing.aspx | Wave is a customer-level setting; no hard-coded wave logic; readiness check | Yes | Wave 25 VERIFIED-OFFICIAL; Wave 24 SECONDARY |
| K4 | Solution provider | Pass SDK/validator and sandbox/simulation tests; per-unit CSID and keys. Directory listing reportedly optional (verify) | https://zatca.gov.sa/en/E-Invoicing/SolutionProviders/Pages/SolutionProvidersDirectory.aspx | Sandbox test plan in [e-invoicing.md](e-invoicing.md); secure key storage | Yes | SECONDARY |
| K5 | VAT | 15% from 2020-07-01, monthly/quarterly filing | https://zatca.gov.sa/en/RulesRegulations/Taxes/Pages/default.aspx (not fetched) | Tax codes, return data, reports, reverse charge | Yes | UNVERIFIED |
| K6 | VAT invoice content | Art. 53 VAT Implementing Regulations fields | https://zatca.gov.sa/en/HelpCenter/guidelines/Documents/Guideline-for-Tax-Invoicing-and-Records-under-VAT-Provisions.pdf | Field validation | Yes | SECONDARY |
| K7 | Arabic on invoices | Tax invoice must include relevant details in Arabic (may be bilingual) | https://zatca.gov.sa/en/HelpCenter/guidelines/Documents/Input%20Tax%20Deduction.pdf | Bilingual templates; Arabic names/addresses stored separately; correct shaping in PDF | Yes | SECONDARY |
| K8 | Hijri date | No official requirement found; XML uses Gregorian (UNVERIFIED) | none found | Gregorian as source of truth; Hijri display later if confirmed | Later | UNVERIFIED |
| K9 | Record retention | Commonly cited 6 years (do not rely) | e-invoicing resolution https://zatca.gov.sa/en/E-Invoicing/Introduction/LawsAndRegulations/Documents/E-Invoicing%20Implementation%20Resolution_EN.pdf (not read) | Immutable archive of signed XML + PDF/A; configurable period | Yes (archive) | UNVERIFIED |
| K10 | Zakat / CIT | Zakat 2.5% / CIT 20% [rates not confirmed]; returns within 120 days of year end (snippets) | https://zatca.gov.sa/en/MediaCenter/News/Pages/Submit-CIT-Return-for-2025.aspx | Trial balance and zakat base worksheet export only | Later | SECONDARY |
| K11 | Withholding tax | Payments to non-residents | none | Tax code flag on AP | Later | UNVERIFIED |
| K12 | GOSI | Contribution rates reported (cohorts, step-ups, ceiling SAR 45,000); sources conflict | https://www.gosi.gov.sa (not fetched) | Effective-dated rate tables, not hard-coded | Yes (config) | UNVERIFIED |
| K13 | Mudad / WPS | Payroll file for bank | https://mudad.com.sa ; https://hrsd.gov.sa (not fetched) | WPS file export; direct API later | Yes (export) | UNVERIFIED |
| K14 | Qiwa / Nitaqat | Contracts, Saudization | https://qiwa.sa (not fetched) | Employee fields now, dashboard later | Later | UNVERIFIED |
| K15 | Labour law | EOSB, leave, notice | https://laws.boe.gov.sa (not fetched) | Configurable EOSB, leave accrual | Later | UNVERIFIED |
| K16 | PDPL | Royal Decree M/19 (2021), amended M/148 (2023); consent, rights, breach notice, records; in force 2023-09-14, enforced 2024-09-14 (secondary) | https://sdaia.gov.sa ; https://dgp.sdaia.gov.sa (not fetched) | Consent/purpose records, DSAR export/delete, breach log, retention, processor agreements | Yes (basics) | SECONDARY |
| K17 | PDPL transfers | Adequacy or safeguards for transfers outside KSA; sources conflict on regulation versions | https://www.dentons.com/en/insights/alerts/2025/may/15/saudi-arabias-framework-for-cross-border-data-transfers | KSA data in-Kingdom or transfer mechanism; per-tenant region | Yes (hosting decision) | UNVERIFIED |
| K18 | NCA ECC/CCC | 2024 versions; applicability to private SMEs and us depends on sector | https://nca.gov.sa/en/regulatory-documents/controls-list/ccc/ | Keep CCC-aligned baseline; in-Kingdom option | Later (baseline yes) | UNVERIFIED |
| K19 | CST cloud registration | Whether a SaaS needs registration | https://www.cst.gov.sa (not fetched) | Ask counsel | Later | UNVERIFIED |

## UAE
| ID | Area | Requirement (short) | Source (accessed 2026-11-04) | Effect on product | v1 must-have | Status |
|---|---|---|---|---|---|---|
| U1 | E-invoicing law | Ministerial Decisions 243 and 244 of 2025; MD 66 of 2026 amends MD 244 Art. 5(1)(a); issued 2025-09-29 (secondary); voluntary pilot from 2026-07-01 | https://mof.gov.ae/wp-content/uploads/2025/09/Ministerial-Decision-No.-244-of-2025-on-the-Implementation-of-the-Electronic-Invoicing-System.pdf (PDF not parsed) | Peppol-ready architecture; ASP integration | Yes (design) | SECONDARY |
| U2 | Phases | Revenue >= AED 50m: ASP by 2026-10-30, go-live 2027-01-01. Below AED 50m: ASP by 2027-03-31, go-live 2027-07-01. Government: ASP 2027-03-31, go-live 2027-10-01. MoF guidelines v1.1 reportedly still show an older date (conflict) | https://gulfnews.com/business/corporate-tax/uae-scraps-e-invoicing-pre-approval-ahead-of-october-deadline-heres-why-1.500707895 | Customers need an ASP by 2027-03-31 for July 2027; confirm on MoF/FTA before telling customers | Yes | SECONDARY, conflicting |
| U3 | Model | DCTCE / Peppol 5-corner, PINT-AE (UBL-based) | MoF/FTA guidelines not retrieved; mof.gov.ae/e-invoicing returned 404 | PINT-AE XML via ASP; inbound invoices; status handling | Yes (via partner) | UNVERIFIED |
| U4 | ASP list | Official list not found | check MoF/FTA e-invoicing page | Partner with 1-2 ASPs | Yes (partner choice) | UNVERIFIED |
| U5 | VAT | 5%; mandatory registration AED 375,000, voluntary AED 187,500; register within 30 days | https://tax.gov.ae/en/taxes/Vat/vat.topics/registration.for.vat.aspx | Tax codes, TRN, VAT 201 data export | Yes | Snippets of official pages; filing frequency UNVERIFIED |
| U6 | Tax invoice content | AED amounts, unit price, qty, VAT rate/amount, exchange rate; simplified if <= AED 10,000 or unregistered recipient | https://tax.gov.ae/-/media/Files/FTA/links/Legislation/VAT/03-Cabinet-Decision-52-of-2017.pdf | Field validation; AED equivalent | Yes | UNVERIFIED current |
| U7 | Arabic on invoices | No official source found; often cited as not mandatory (UNVERIFIED) | none | Bilingual templates configurable | Yes (bilingual) | UNVERIFIED |
| U8 | Corporate tax | 9% over AED 375,000 taxable income; Federal Decree-Law 47 of 2022; from financial years starting on/after 2023-06-01 (secondary) | https://tax.gov.ae (not fetched) | Tax adjustment hooks, trial balance export | Later | SECONDARY |
| U9 | Small Business Relief | Revenue <= AED 3m; extension to 2029 claimed (Decision 131 of 2026) not confirmed | secondary sources in research row U9 | Flag and revenue tracking | Later | UNVERIFIED |
| U10 | WPS | MOHRE approved channels, SIF file | https://www.mohre.gov.ae (not fetched) | SIF export | Yes (export) | UNVERIFIED |
| U11 | Gratuity | Federal Decree-Law 33/2021 (rates UNVERIFIED) | https://uaelegislation.gov.ae (not fetched) | Configurable accrual | Later | UNVERIFIED |
| U12 | Emiratisation | Targets and contributions reported; amounts conflict | https://www.mohre.gov.ae (not fetched) | Nationality flag, headcount report | Later | UNVERIFIED |
| U13 | UAE PDPL | FDL 45/2021, in force 2022-01-02 (secondary); executive regulations reportedly not issued | https://uaelegislation.gov.ae (not fetched) | Same privacy toolkit as KSA | Yes (basics) | SECONDARY |
| U14 | DIFC / ADGM | DIFC Law 5/2020; ADGM Regulations 2021 | https://www.difc.ae ; https://www.adgm.com | Region-specific notices if customers there | Later | UNVERIFIED |
| U15 | Data residency | No general UAE localisation law confirmed; sector rules exist | none | Offer UAE region | Yes (offer region) | UNVERIFIED |
| U16 | Retention | Commonly 5 years VAT; 15 real estate; 7 CT (UNVERIFIED) | none | Configurable retention, immutable archive | Yes | UNVERIFIED |
| U17 | Hijri | No requirement found | none | None in v1 | No | UNVERIFIED |

## Egypt (operating market, launch order KSA, UAE, Egypt)
Founder requirement: the platform operates in KSA, UAE and Egypt. Adding Egypt changes nothing about the KSA-first launch: KSA remains first for customers, UAE second, Egypt third ([../strategy/02-niche-and-launch-country.md](../strategy/02-niche-and-launch-country.md)). The research file has NO Egypt rows; every row below is research needed, with no facts recorded. When researched, record each fact with URL and access date. Country packs are specified in [../architecture/country-packs.md](../architecture/country-packs.md) and calendars in [../architecture/calendars-and-locale.md](../architecture/calendars-and-locale.md) (written by another agent).
| ID | Area | Question to research | Effect on product (to confirm) | v1 must-have for Egypt | Status |
|---|---|---|---|---|---|
| E1 | E-invoicing | Is there a national e-invoicing mandate, which authority, which phases and thresholds, document format, signing, portal/API, vendor obligations, sandbox | Egypt e-invoicing component and sandbox plan (see [e-invoicing.md](e-invoicing.md)) | Yes if mandate exists | research needed |
| E2 | VAT | Rate(s), registration threshold, filing cycle, invoice content, special regimes, zero-rated/exempt lists | Tax codes, return data, validation | Yes | research needed |
| E3 | Corporate tax | Rates, filing, small-business regimes, withholding | Trial balance and tax worksheet exports | Later | research needed |
| E4 | Payroll and labour | Social insurance, payroll tax, wage payment rules, end-of-service, leave, official reporting formats | Payroll component rates and file exports | Later | research needed |
| E5 | Data protection | Law, regulator, consent, transfers, residency, breach notice, registration of processors | Privacy toolkit, region choice ([data-protection-and-residency.md](data-protection-and-residency.md)) | Yes (basics) | research needed |
| E6 | Language and document rules | Is Arabic required on invoices/contracts; bilingual rules; Arabic numerals (Western vs Eastern Arabic digits) practice | Templates, number system setting | Yes | research needed |
| E7 | Currency | Currency code, rounding, exchange-rate rules, foreign-currency invoicing restrictions, volatility handling | Multi-currency and rate source | Yes | research needed |
| E8 | Hosting | In-country cloud region availability; sector rules | Region option | Yes | research needed |
| E9 | Company law and entity | Local entity/registration to contract and invoice; commercial register identifiers | Sign-up fields; [../legal/checklist.md](../legal/checklist.md) | Yes | research needed |
| E10 | Retention | Tax and accounting record periods | Archive config | Yes | research needed |
| E11 | Sector rules | Health, banking, government | Scope exclusions | Later | research needed |

## Leads from co-founder research (UNVERIFIED; verify against official sources before use)
| Market | Lead | Product effect |
|---|---|---|
| KSA (ZATCA Phase 2) | Cryptographic stamps, ECDSA secp256k1 signatures, invoice hashing, UBL 2.1 XML output | Certified invoice component; the model never builds or signs invoices |
| Egypt (ETA) | E-invoicing extensions, digital signatures, official unified chart of accounts, withholding-tax integrations | Egypt country pack scope (E1, E2, E3); chart of accounts template |
| UAE (FTA) | Corporate tax 9% and VAT 5% accounting rules | Tax codes and corporate-tax worksheet in the UAE pack (see U-rows above for sourced items) |
Principle (all three): statutory requirements ship as certified country packs; the model never calculates tax.

## Calendar and work-week
Calendars, week and time are per-company settings (Settings > Company calendar and week, [../product/app-screens.md](../product/app-screens.md)); the country chosen at sign-up supplies defaults. Nothing below is confirmed by the research unless stated; all rows UNVERIFIED, research needed with official sources.
| Topic | KSA | UAE | Egypt |
|---|---|---|---|
| Calendar used in commerce and tax | Gregorian in practice (UNVERIFIED); research notes ZATCA XML uses Gregorian ISO dates (UNVERIFIED, K8) | Gregorian (research: UAE uses Gregorian, U17, UNVERIFIED) | Gregorian in practice (UNVERIFIED) |
| Where Hijri matters | Saudi official context and some contracts (UNVERIFIED); zakat year possibly Hijri-based (K10, research mentions Hijri for zakat year, UNVERIFIED); GOSI/Qiwa outputs (K8, UNVERIFIED); religious dates | Religious dates and holidays; no invoice requirement found (U17) | Religious dates and holidays (UNVERIFIED) |
| Other calendars | none known | none known | Coptic possibly in some contexts (UNVERIFIED) |
| Default weekend / work-week | research needed (do not hard-code) | research needed (reported changes in recent years, UNVERIFIED) | research needed |
| Public holidays | Research needed; fixed vs Hijri-based holidays | Same | Same |
| Moon-sighting uncertainty | Hijri holidays (e.g. Eid) depend on moon sighting and are announced late; holiday calendar needs manual override | Same | Same |
| Ramadan hours | Reduced hours are common (UNVERIFIED); per-company setting | Same | Same |
| Time zone | research needed | research needed | Daylight saving time status UNVERIFIED; handle by time-zone database, not fixed offset |
| Number system | Western vs Eastern Arabic digits: per-company setting | Same | Same |
Design rule: Gregorian is the source of truth in storage; Hijri (and Coptic if needed) are display and rule inputs; weekend, working days, hours, holidays and fiscal year are effective-dated company settings, never code constants.

## Other markets: research needed
Bahrain, Oman, Kuwait, Qatar, others. Same categories as Egypt above (indirect tax, e-invoicing, language and calendar, payroll, data protection, hosting, company law, retention, sector rules). No facts recorded. Trigger: next-market decision at gate G5 or earlier by ADR.

## Vendor vs client obligations
See the research section 4 ([../research/03-regulations.md](../research/03-regulations.md)); tracked in [vendor-certification.md](vendor-certification.md).

## Open legal questions
12 questions listed in the research section 5; carried to [../legal/checklist.md](../legal/checklist.md).
