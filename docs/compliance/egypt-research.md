# Egypt market research (CMP-027)

Status: draft
Owner: eldon

Scope: e-invoicing and e-receipt, VAT, data protection, payroll, plus retention, language, currency and hosting where found. Access date for every source below: 2026-11-18. Not legal or tax advice; every item needs local counsel or accountant confirmation (table at the end).

Confidence labels: **VERIFIED** = read on the official primary page on the access date. **PRIMARY-SNIPPET** = an official page appeared in a search result but the page itself was not read in full. **UNVERIFIED** = secondary source only (law firm, vendor, calculator site), or sources conflict. Nothing UNVERIFIED enters the product without a primary check. The official ETA home page and the VAT executive regulations returned errors or were not parsed in this pass; the Arabic official texts were not read.

## 1. E-invoicing and e-receipt (ETA)
| # | Finding (short paraphrase) | Source | Label |
|---|---|---|---|
| 1.1 | The Egyptian Tax Authority (ETA) runs an eInvoicing and eReceipt system where taxpayers register documents they issue and receive event notifications; the SDK documents the APIs for taxpayer ERP and POS systems. | https://sdk.invoicing.eta.gov.eg/ | VERIFIED |
| 1.2 | Setup: register a digital taxpayer profile; the administrator (by invitation) registers one or more ERP or POS systems; each registered system gets API access credentials; the system also needs an eSeal X.509 certificate to sign documents. Login returns a session token used for the APIs; optional callbacks for document status. | https://sdk.invoicing.eta.gov.eg/start/ | VERIFIED |
| 1.3 | Signing: CAdES-BES signature, Base64-encoded, over a SHA-256 hash of the canonical (serialised) document in UTF-8; signature added as an element of the document before submission. Page does not mention a hardware token. | https://sdk.invoicing.eta.gov.eg/signature-creation/ | VERIFIED |
| 1.4 | A PreProd (test) environment exists with its own Root CA to trust on test machines only; separate PreProd and Prod URLs for registration portal, invoicing portal, system API and identity service; Postman collections provided. | https://sdk.invoicing.eta.gov.eg/faq/ | VERIFIED |
| 1.5 | ETA home page states all taxpayers had to issue e-invoices from 2022-12-15 and that entities without e-invoices cannot deal with customs from 2023-04-01; SDK docs cite Ministerial Decision 188 of 2020 as the binding decision. Snippets only. | https://www.eta.gov.eg/en/home ; https://eta.gov.eg/en/content/guides-dealing-electronic-invoices-system (search result 2026-11-18) | PRIMARY-SNIPPET |
| 1.6 | E-receipts (B2C, point of sale): receipts are JSON only and not issuer-signed; a buyer national ID becomes mandatory above a configured amount (50,000 EGP for receipt v1.0-1.1, 150,000 EGP for v1.2+); more POS devices are being approved for integration. | https://sdk.invoicing.eta.gov.eg/receiptissuancefaq/ and https://sdk.invoicing.eta.gov.eg/documents/receipt-v1-2/ (snippets); https://www.fonoa.com/resources/country-tax-guides/egypt/e-invoicing-and-digital-reporting | UNVERIFIED (snippet plus vendor) |
| 1.7 | Rollout was in phases (B2B seven phases starting with large taxpayers; B2C from 2022 in five phases); invoices reported on the day issued since 2023-01. Sources give different dates for "all taxpayers" (2022-12, 2023-04, 2023-07). | https://www.fonoa.com/resources/country-tax-guides/egypt/e-invoicing-and-digital-reporting ; https://taxsummaries.pwc.com/egypt/corporate/other-taxes ; https://vatit.com/e-invoicing-guide/egypt/ (403, snippet only) | UNVERIFIED (conflict) |
| 1.8 | Penalties reported: late reporting EGP 20,000 to 100,000; failing to archive invoices five years up to EGP 50,000; evasion fines and prison. | https://www.fonoa.com/resources/country-tax-guides/egypt/e-invoicing-and-digital-reporting | UNVERIFIED |
| 1.9 | A vendor page mentions a 2026 decree adjusting the phased programme. No primary text found; one search conflated it with an Omani decision. Treat as unknown. | https://vatit.com/e-invoicing-guide/egypt/ (snippet) | UNVERIFIED |
| 1.10 | Vendor sources say the signing certificate comes from an approved provider and is usually on an HSM token or USB seal. Primary page does not say this. | https://www.storecove.com/blog/en/e-invoicing-regulations-egypt/ (snippet) | UNVERIFIED |

### Not yet read (primary pages to read next)
Document format and serialisation page, UUID rules, document types (invoice, credit, debit), codes lists, API governance and rate limits, integration practices (404 on guessed URL), cancellation and rejection windows, QR content on receipts, taxpayer eSeal certificate issuers and token rules, ETA news for current phases. Start at https://sdk.invoicing.eta.gov.eg/ navigation.

### What a platform for 10-100 staff companies must do (design position, UNVERIFIED until 1.x are read)
- Each tenant registers its own ERP system in the ETA portal and holds its own eSeal certificate; per-tenant keys and credentials follow [../security/threat-model.md](../security/threat-model.md) key custody. Whether a vendor-hosted shared signing service is allowed, or each tenant needs its own token or HSM, is open (counsel question 3).
- Issue immutable documents; corrections by credit or debit note only; submit on the issue day; queue and retry; show ETA rejections as plain messages with the exact field ([e-invoicing.md](e-invoicing.md) common rules).
- Pull the ETA submission, UUID and status back into the ledger; archive the signed document and rendering for the retention period (section 5).
- E-receipts: needed only for tenants selling to consumers at a point of sale; POS integration scope is a G2 decision for the Egypt pack (CMP-028).
- Vendor certification: no vendor listing or certification scheme was found in the official SDK pages read; a registered-system step per taxpayer exists (1.2). Whether ETA requires solution-provider approval is open (counsel question 4).
- Reuse: check whether an open-source Egypt e-invoice app exists for Frappe and its licence before building (research needed, same method as [zatca-erpgulf-evaluation.md](zatca-erpgulf-evaluation.md)).
- Deterministic code: document serialisation, hashing, signing, submission and status handling. Configuration: phase and tenant readiness, ETA environment URLs, document and code lists (effective-dated), credentials references. Never AI-written ([../../AGENTS.md](../../AGENTS.md) principle 3).

## 2. VAT
| # | Finding | Source | Label |
|---|---|---|---|
| 2.1 | Standard VAT 14%; reduced 5% for production machinery and equipment; exports zero-rated under conditions; some exempt supplies; registration above EGP 500,000 annual taxable turnover; monthly electronic returns with return and payment due by the end of the following month; reverse charge on services from non-resident suppliers. | https://taxsummaries.pwc.com/egypt/corporate/other-taxes | UNVERIFIED (secondary) |
| 2.2 | A separate schedule (table) tax applies once on listed goods and services, in addition to VAT for some items. | same | UNVERIFIED |
| 2.3 | Law 157 of 2025 (issued 2025-07-17) moved construction services from a 5% schedule tax to 14% VAT with input recovery; the change had to be reflected in e-invoice data for ongoing contracts, so ERP configuration may change. | https://taxnews.ey.com/news/2025-2316-egypt-introduces-significant-updates-to-vat-provisions | UNVERIFIED |
| 2.4 | Law 149 of 2026 (published 2026-07-28 per secondary sources) reportedly sets 5% VAT for machinery, equipment and medical devices used in production or service provision. | https://eg.andersen.com/egypts-vat-amendments-2026/ ; https://lookuptax.com/tax-changes/egypt/vat-exempt-schedule-law-149-2026 (snippets) | UNVERIFIED |
| 2.5 | VAT executive regulations (updated 2023-01-15) are published by ETA as an English PDF; not parsed in this pass. | https://www.eta.gov.eg/sites/default/files/2024-02/VAT-Executive-Regulations-English.pdf | PRIMARY-SNIPPET |
| 2.6 | A refund-period cut from six to four months was described as proposed; enactment unknown. Registration threshold exceptions (schedule goods, importers, exporters, agents) reported by a tax-lookup vendor. | https://eg.andersen.com/egypts-vat-amendments-2026/ ; https://lookuptax.com/docs/country/egypt-vat-guidelines-indirect-tax | UNVERIFIED |

Platform position: tax codes (rate, schedule tax, exemption, zero-rate) are effective-dated configuration in the Egypt pack; the VAT return data set and e-invoice tax lines are deterministic code. Rate changes in 2025 and 2026 show the code table must change without a release. Mandatory invoice content, withholding and corporate tax are not covered here (country-matrix E3 stays open).

## 3. Data protection (Law 151 of 2020)
| # | Finding | Source | Label |
|---|---|---|---|
| 3.1 | Personal Data Protection Law 151 of 2020 and its executive regulations; the regulations were reported issued 2025-11-01 as Ministerial Decision 816/2025 and made public 2025-12-25; a one-year compliance period runs from issuance (expected enforcement about 2026-11-01, possibly later). One search result gave a conflicting number (81). | https://cms.law/en/are/legal-updates/egypt-s-pdpl-executive-regulations-issued-one-year-compliance-countdown-begins ; https://chambers.com/articles/a-first-look-at-egypt-s-personal-data-protection-executive-regulations | UNVERIFIED |
| 3.2 | Regulator: the Personal Data Protection Centre (PDPC). It issues licences for controllers and processors (reported three-year validity, review about 90 working days) and separate permits for cross-border transfer, electronic direct marketing and visual surveillance. | CMS link above | UNVERIFIED |
| 3.3 | Transfers outside Egypt, including to cloud environments, reportedly need prior PDPC permit; a future adequacy framework is foreseen; transfer fee reported at half the licence fee. | CMS link above ; https://www.legal500.com/guides/hot-topic/strategic-challenges-and-opportunities-in-cross-border-data-transfers-under-egypts-personal-data-protection-regime | UNVERIFIED |
| 3.4 | Legal entities appoint a DPO registered with the PDPC. Breach notice to the PDPC within 72 hours; to individuals within three days after the PDPC notice. | CMS link above | UNVERIFIED |
| 3.5 | Law text mirrored by a law firm (English translation, not official). | https://eg.andersen.com/wp-content/uploads/2026/02/Law-No.-151-of-2020.pdf | UNVERIFIED |
| 3.6 | Law reportedly does not apply to entities regulated by the Central Bank if CBE rules are followed; a 2026 CBE digital identity rule asks banks to align outsourcing and data protection. | https://resourcehub.bakermckenzie.com/en/resources/cloud-compliance-center/emea/egypt/topics/data-privacy-and-security ; https://www.bakermckenzie.com/en/insight/publications/2026/09/egypt-new-digital-financial-identity-system-rules-for-ekyc (snippets, may be stale) | UNVERIFIED |

Residency position (provisional): the cross-border permit reading (3.3) is the biggest finding. If true, tenant personal data hosted outside Egypt, and any foreign model API call carrying personal data, needs a PDPC permit; hosting in an Egyptian region removes the question for storage only. In-country cloud region availability (E8) was not researched. Interim rules in [data-protection-and-residency.md](data-protection-and-residency.md) apply: minimise, redact, route by region, do not claim "data never leaves the country". We are processor for tenants, so a PDPC processor licence, DPO and DPA are likely (counsel question 5). Employee data in the HR module is personal data.
Product effect: consent and DSAR tooling, breach log with a 72-hour clock, region setting per tenant (ADR-0006). Configuration: region, retention, notice recipients. Deterministic code: audit trail, breach timer, export and delete.

## 4. Payroll and labour
| # | Finding | Source | Label |
|---|---|---|---|
| 4.1 | Social insurance (Law 148 of 2019): employee 11%, employer 18.75% of insurable wage. | https://eg.andersen.com/social-insurance-in-egypt/ ; https://www.mondaq.com/employee-rights-labour-relations/1810754/social-insurance-in-egypt | UNVERIFIED |
| 4.2 | Insurable wage floor and ceiling from January 2026 reported as EGP 2,700 and EGP 16,700 (previously 2,300 and 14,500); a yearly step to 2028 is claimed once and unconfirmed. | https://www.bdo.global/en-gb/insights/tax/expatriate-tax/egypt-maximum-and-minimum-salaries-subject-to-social-insurance-increased ; https://www.businesstodayegypt.com/Article/1/6950/Egypt-s-Social-Insurance-Authority-announces-increase-in-wages-starting | UNVERIFIED |
| 4.3 | Salary income tax: annual personal exemption EGP 20,000 (was 15,000) and progressive bands from 0% to 27.5% (top band above EGP 1,200,000); band rates differ between sources and may be shown before or after exemption; legal basis cited as Law 7 of 2024 amending Law 91 of 2005. | https://www.deloitte.com/middle-east/en/services/tax/perspectives/amendment-to-tax-brackets-and-annual-personal-exemption.html ; https://eg.andersen.com/personal-income-tax/ | UNVERIFIED (conflict on bands) |
| 4.4 | New Labour Law 14 of 2025 in force from 2025-09-01, replaces Law 12 of 2003: longer maternity leave (120 days), dismissal needs a court ruling, permanent contract presumption, at least 3% yearly raise of insurable wage, formal remote and part-time work, defined termination compensation formula. | https://www.ey.com/en_gl/technical/tax-alerts/egypt-enacts-new-labor-law-with-changes-affecting-employers-beginning-1-september-2025 ; https://www.clydeco.com/en/insights/2025/05/egypt-new-labour-law | UNVERIFIED |
| 4.5 | Not found: wage payment method rules, overtime, end-of-service formula, official payroll reporting formats and portals (social insurance registration and monthly filing), payroll tax withholding filing form and cycle. | n/a | research needed |

Platform position: payroll is "Later" in the matrix (E4) but 10-100 staff owners expect it. Rates, floors, ceilings, bands and exemptions are effective-dated configuration with an update path from the regulation-watch process ([regulation-watch.md](regulation-watch.md)); the calculation (insurable wage clamp, contributions, taxable base, progressive tax, end-of-service) is deterministic, tested code with counsel-signed test cases. Because 4.2 and 4.3 change yearly, nothing is hard-coded.

## 5. Retention, language, currency, hosting
| # | Finding | Source | Label |
|---|---|---|---|
| 5.1 | Tax records kept five years from the date of the return (six in evasion cases); electronic accounting books accepted under the 2021 executive regulation; Law 7 of 2025 amended Law 206 of 2020, effect on retention unchecked. | https://taxnews.ey.com/news/2020-2532-egypt-introduces-unified-tax-procedures-law ; https://www.pwc.com/m1/en/tax/documents/2021/egypt-egyptian-government-issues-executive-regulation-286-unified-tax-procedures-law-206-2020.pdf | UNVERIFIED |
| 5.2 | Currency: EGP is the legal currency (general knowledge, not sourced here). Foreign-currency invoicing rules, rounding and rate source not researched. | none | research needed |
| 5.3 | Arabic requirement on invoices and contracts, digit style, calendar: not researched (E6). | none | research needed |
| 5.4 | CBE outsourcing and cloud: regulated banks face prior approval and disclosure of data location; telecom regulator rules did not regulate foreign data centres at the time of the source. Banks are out of near-term scope. | https://resourcehub.bakermckenzie.com/en/resources/cloud-compliance-center/emea/egypt/topics/regulated-cloud-outsourcing ; https://resourcehub.bakermckenzie.com/en/resources/cloud-compliance-center/emea/egypt/topics/permissibility-of-cloud | UNVERIFIED (snippets) |
| 5.5 | In-country cloud region, work-week, public holidays, time zone, entity and commercial register rules (E8, E9, calendar table): not researched. | none | research needed |

## 6. What is code, what is configuration
| Item | Deterministic code | Effective-dated configuration |
|---|---|---|
| E-invoice | Serialise, hash, CAdES-BES sign, submit, status, retry, archive | ETA endpoints, phase readiness, code lists, document versions |
| VAT | Tax lines, return data set, reverse charge, validation | Rates, schedule tax, exemptions, threshold |
| Payroll | Clamp, contributions, tax bands, end-of-service | All rates, floors, ceilings, exemptions |
| Privacy | Audit, breach timer, export and delete, consent log | Region, retention, notice contacts, permit status per tenant |

## 7. Open risks
1. The cross-border PDPC permit (3.3) may block foreign hosting and foreign AI calls for Egyptian tenants; enforcement date uncertain (3.1).
2. Egypt e-invoice phase dates conflict (1.7) and a 2026 change is unread (1.9).
3. Per-tenant signing certificate and token rules may make a hosted signing service impractical (1.10).
4. Frequent rate changes (2.3, 2.4, 4.2, 4.3) mean stale config produces wrong invoices or payslips.
5. Only secondary sources for VAT, payroll and privacy; the Arabic official texts were not read.
6. Retention and Arabic-language rules unknown.

## 8. Questions for a local counsel or accountant
| # | Question | Topic | Why it matters |
|---|---|---|---|
| 1 | What is the current ETA e-invoice phase list and are all VAT-registered and non-registered small taxpayers now in scope? Any 2026 decree changing it? | E-invoice | Scope of Egypt pack |
| 2 | Is the e-receipt system required for B2B-only tenants, and for which sectors? | E-receipt | POS scope |
| 3 | May a platform sign on behalf of a tenant with a hosted eSeal key, or must each tenant hold a token or HSM? Who issues certificates? | Signing | Architecture, key custody |
| 4 | Does ETA approve or list solution providers, or is registering the system in the taxpayer profile enough? | Certification | Go-live path |
| 5 | Must we hold a PDPC processor licence and DPO, and from what date? Is the enforcement date 2026-11-01 or later? | Privacy | Entity and cost |
| 6 | Does hosting outside Egypt, or a call to a foreign AI model API, need a PDPC cross-border permit? Is there an adequacy list or exemption for business-necessary transfers? | Residency | Hosting region, AI routing |
| 7 | Confirm VAT rates, schedule tax, registration threshold, filing deadlines and invoice mandatory content for 2026. | VAT | Tax codes |
| 8 | Confirm 2026 social insurance rates, floors and ceilings, tax bands and exemption, and the official filing process and formats. | Payroll | Payroll component |
| 9 | Confirm end-of-service formula, overtime, wage payment method and leave rules under Law 14 of 2025 and its regulations. | Labour | Payroll component |
| 10 | Confirm record retention periods for invoices, books and payroll, and whether the archive must be in Egypt. | Retention | Archive config |
| 11 | Is Arabic required on invoices and contracts; are foreign-currency invoices allowed? | Language, currency | Templates, multi-currency |
| 12 | What entity or registration must we have to contract with and invoice Egyptian tenants? | Company | LEG-010, LEG-003 |
