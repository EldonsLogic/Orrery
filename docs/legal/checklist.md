# Legal checklist

Status: draft
Owner: eldon

Not legal advice. Everything here needs counsel. Status values: todo / doing / done / blocked. Plan IDs (LEG-NNN) live in [../PLAN.md](../PLAN.md).

| # | Item | Why | Notes | Status |
|---|---|---|---|---|
| 1 | Founders' agreement (equity, roles, vesting, decision rights, leaver terms) | Two founders, no agreement on record in the repo | Needed before external money | todo |
| 2 | Entity and bank account | Contract, invoice, hire, receive funds | Recommended setup pending counsel: UAE entity selling to KSA, KSA tenants hosted in-Kingdom ([../strategy/02-niche-and-launch-country.md](../strategy/02-niche-and-launch-country.md)); whether it may contract/invoice KSA clients and need Saudi VAT registration is UNVERIFIED | todo |
| 3 | IP assignment (founders and contractors to the company) | Clean ownership for investors | Include prior prototype code (change engine) and its history | todo |
| 4 | GPL boundary review | ERPNext/HRMS are GPL-3; run as SaaS only | Confirm separate services over API are not derivative; never distribute engine without review; write down the architecture rule ([../strategy/04-architecture-and-seed.md](../strategy/04-architecture-and-seed.md)) | todo |
| 5 | Open-source licence register | Principle 1 | Record every adopted licence (MIT ERPGulf app, Frappe MIT, etc.); avoid AGPL lavaloon app | doing |
| 6 | Trademark and domain clearance | Working name Orrery is not cleared (ADR-0001) | Search in KSA/UAE and key classes; domains; avoid "ERPNext"/"Frappe" in name and ads | todo |
| 7 | Customer contract (master agreement) | Revenue | Includes: SaaS scope, setup milestones, data ownership and export, anonymised pattern reuse clause (licence to reuse de-identified Blueprint patterns and components), no training on tenant data, SLAs TBD, liability cap for compliance output, human review gate language, termination and deletion | todo |
| 8 | Pilot agreement (paid, about 50%) | First customers | Case-study rights, reuse clause, data handling, feedback | todo |
| 9 | Terms of service | Self-serve sign-up | Acceptable use, AI limitations, account rules | todo |
| 10 | Privacy notice (website, app) | PDPL | Arabic and English; our controller role | todo |
| 11 | Data Processing Agreement (DPA) | We are processor for tenants | Sub-processors, security, breach notice, transfers, audit, deletion | todo |
| 12 | Cookie / consent policy and banner text | PDPL consent for analytics | See [../product/website.md](../product/website.md) | todo |
| 13 | Brand asset licence and user content terms | Tenant uploads logos | Tenant warrants rights; licence to display; takedown; see [../security/brand-asset-upload-security.md](../security/brand-asset-upload-security.md) | todo |
| 14 | Sub-processor list and notice process | DPA | From [../security/hosting-rules.md](../security/hosting-rules.md) | todo |
| 15 | Employment/contractor templates | Hiring | Confidentiality, IP, AI tool use | todo |
| 16 | Insurance (cyber, professional liability) | Compliance output risk | Research | todo |
| 17 | Tax position of our own sales (VAT on our invoices, withholding) | We must invoice compliantly ourselves | UNVERIFIED | todo |
| 18 | Third-party content/AI terms review | Model provider terms: no training, retention, regions | Per provider | todo |

## Counsel question list (from the research)
Carried from [../research/03-regulations.md](../research/03-regulations.md) section 5 (12 questions):
1. ZATCA vendor registration/approval beyond SDK and sandbox conformity.
2. UAE ASP accreditation, integration without being an ASP, liability split.
3. Final UAE e-invoicing schedule (MD 66 of 2026 vs guidelines v1.1), B2C exclusion.
4. Arabic and Hijri requirements for invoices in both countries.
5. Retention periods (KSA, UAE) and who bears archiving duty.
6. PDPL transfer mechanism for hosting outside KSA; KSA-region host mandatory?; SDAIA processor registration; DPO.
7. NCA ECC/CCC and CST cloud rules for us as a SaaS vendor.
8. UAE PDPL executive regulations; DIFC/ADGM scope.
9. Small Business Relief extension claim; GOSI step-ups; Emiratisation amounts.
10. AI features: client data to third-party LLMs across borders under PDPL; model training.
11. Whether payroll file generation or tax data preparation makes us a regulated service.
12. Local entity or commercial registration to contract and invoice in SAR/AED.
Added by this repo:
13. GPL-3 boundary for our architecture (item 4 above).
14. Anonymised reuse clause wording and enforceability.
15. Liability and disclaimers for AI-drafted configuration approved by humans.
16. Trademark policy limits when we mention ERPNext/Frappe compatibility.

## Egypt (added; all research needed, no facts recorded)
| # | Item | Status |
|---|---|---|
| E-1 | Entity, commercial registration and bank needed to contract and invoice Egyptian customers; relation to the chosen entity | research needed |
| E-2 | Tax position of our own sales into Egypt (VAT, withholding) | research needed |
| E-3 | Data protection law, processor registration, cross-border transfer and residency | research needed |
| E-4 | E-invoicing vendor obligations and any registration for software vendors | research needed |
| E-5 | Arabic and language rules for contracts and invoices; governing law and dispute venue in customer contract | research needed |
| E-6 | Currency and payment-collection rules for subscriptions | research needed |
| E-7 | Trademark and domain clearance in Egypt | research needed |
Counsel questions 17-20: (17) entity for Egypt; (18) e-invoicing vendor duties; (19) PDPL-equivalent transfer rules for hosting and AI processing; (20) contract language and currency rules.
