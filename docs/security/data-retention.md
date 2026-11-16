# Data retention and deletion

Status: draft
Owner: eldon
Approved by: pending (partner review with a different model; counsel in each market under LEG-003)

Plan ID: DAT-001. Says how long the platform keeps each kind of data, when and how it deletes, and what survives deletion. Classes are in [data-classification.md](data-classification.md). Feeds DAT-003, DAT-006, DAT-007, OPR-012, OPR-014 and the runbook "Offboard, export and delete tenant" in [../runbooks/README.md](../runbooks/README.md).

**This is not legal advice and not a statement of what the law requires of a customer.** It records what the platform will do by default and the sources found so far. Counsel (LEG-003) must confirm every per-country figure before any launch in that market. Nothing here is built.

## 1. Rules that hold everywhere
1. **Periods are configuration, never model output.** Every retention period is a value in the country pack ([../architecture/country-packs.md](../architecture/country-packs.md)), versioned, reviewed by PR, and read by deterministic code. A model never computes, proposes at run time or overrides a period.
2. **Longest applicable rule wins.** Where two rules cover one record (for example VAT and commercial-books law), the pack stores both and the engine applies the later end date.
3. **Statutory minimum first, then minimise.** Data with a statutory minimum is kept at least that long. Data with none is kept only while its purpose lasts, and personal data is deleted or anonymised when the purpose ends.
4. **Legal hold beats deletion. Deletion beats convenience.** Nothing under hold is deleted by any job. Nothing is kept "in case it is useful".
5. **The tenant is the controller and the taxpayer.** The duty to keep tax and accounting records sits with the tenant (UNVERIFIED whether any duty falls on the platform as processor; legal checklist question 5 in [../legal/checklist.md](../legal/checklist.md)). The platform keeps the records while the tenant is a customer and hands them over at exit.
6. **Deletion is a logged, deterministic job** with a verification step and a certificate (DAT-007). An unverified deletion is a failed deletion.
7. **Unverified means not relied on.** A row marked SECONDARY or UNVERIFIED ships in a pack only as "unset"; the engine then refuses automatic deletion for that category in that market (fail closed: keep, do not delete).

## 2. Confidence key
| Mark | Meaning |
|---|---|
| OFFICIAL | Text read on a government site on the access date |
| TEXT | Full article read, but in a non-official copy or translation; official text still to check |
| SECONDARY | Law-firm or adviser summary only |
| UNVERIFIED | No usable source found, sources conflict, or not researched |

All sources below were accessed 2026-11-16. Amendments after the copy read are not checked unless stated.

## 3. Statutory retention by market
"Platform default" is what the pack will hold once counsel confirms. Until then it is unset (rule 7).

### 3.1 Saudi Arabia
| ID | Category | Rule found | Source | Confidence | Platform default |
|---|---|---|---|---|---|
| KR-1 | VAT invoices, books, records, accounting documents | Kept a minimum of 6 years from the end of the tax period they relate to (VAT Implementing Regulations, Art. 66(1)) | https://zatca.gov.sa/en/RulesRegulations/Taxes/Documents/Implmenting%20Regulations%20of%20the%20VAT%20Law_EN.pdf | OFFICIAL (English edition; amendments approved in 2025 not checked against it) | 6 years from period end |
| KR-2 | Capital-asset records | Adjustment period plus 5 years from acquisition; adjustment period is 6 years for movable and 10 for immovable assets (Art. 66(1), Art. 52): 11 and 15 years | Same | OFFICIAL | 11 or 15 years from acquisition, by asset type |
| KR-3 | Language and place of records | Records in Arabic; kept in the Kingdom physically or electronically with server access from a terminal in the Kingdom; tamper controls; producible on request (Art. 66(2), 66(3)) | Same | OFFICIAL | KSA tenants hosted in a KSA region; Arabic records |
| KR-4 | E-invoices and e-notes | Retained in the form and by the procedures of the e-invoicing regulations (Art. 66(3)(h)). Period read as KR-1; the e-invoicing regulation itself was not read | Same | OFFICIAL for the pointer; UNVERIFIED for format detail | Immutable signed XML and rendered PDF kept as KR-1 |
| KR-5 | Commercial books, correspondence and documents | Kept at least 10 years (Law of Commercial Books, Art. 8) | https://misa.gov.sa/app/uploads/2025/07/Law-of-Commercial-Books.pdf | OFFICIAL (official translation, last update 2022-06-16; later repeal or amendment not checked) | 10 years |
| KR-6 | Zakat return documents | Kept within the Kingdom no less than 10 years (Implementing Regulations for Zakat Collection, Art. 110) | https://zatca.gov.sa/en/RulesRegulations/Documents/ZAKAT%20COLLECTION.pdf | OFFICIAL | 10 years |
| KR-7 | Income-tax records | 10 years reported without an article | none usable | UNVERIFIED | unset |
| KR-8 | Payroll, wage-protection (Mudad), social-insurance and employment records | No period found | none | UNVERIFIED | unset |
| KR-9 | Audit logs | No statutory period found; applicability of national cybersecurity controls is UNVERIFIED ([../compliance/vendor-certification.md](../compliance/vendor-certification.md)) | none | UNVERIFIED | Platform rule in section 9 |

### 3.2 United Arab Emirates
| ID | Category | Rule found | Source | Confidence | Platform default |
|---|---|---|---|---|---|
| UR-1 | Tax records, accounting records, commercial books (VAT, excise) | 5 years after the tax period for a taxable person; 5 years from the end of the calendar year for others (Cabinet Decision 74 of 2023, Art. 3(1)) | https://uae.shushin.io/taxlaw/taxprocedures/executive-regulation | TEXT (official Ministry of Finance link returned 404; a 2026 amending decision not checked) | 5 years from period end |
| UR-2 | Real-estate records | 7 years from the end of the calendar year (Art. 3(1)(c)) | Same | TEXT | 7 years |
| UR-3 | Extensions | Plus 4 years on dispute, ongoing audit or notified audit; plus 1 year after a voluntary disclosure made in the fifth year (Art. 3(2)) | Same | TEXT | Modelled as a legal hold (section 5), not a fixed period |
| UR-4 | Corporate-tax records | 7 years following the end of the tax period (Federal Decree-Law 47 of 2022, Art. 56) | https://mof.gov.ae/wp-content/uploads/2022/12/Federal-Decree-Law-No.-47-of-2022-EN.pdf | OFFICIAL | 7 years; governs most ledgers under rule 2 |
| UR-5 | E-invoices and e-credit notes | Retention reported to follow the tax procedures rules. Storage place: reports conflict (in the UAE under the 2025 decision; later amendment and guidance reported to allow hosting outside) | https://globaltaxnews.ey.com/news/2025-1964 ; https://globaltaxnews.ey.com/news/2026-0512 | UNVERIFIED | unset; store in the UAE regardless (ADR-0006) |
| UR-6 | Employee files | At least 2 years after end of service (Federal Decree-Law 33 of 2021, as reported) | https://www.clydeco.com/en/insights/2023/01/uae-employment-immigration-landscape-2022-takeaway | SECONDARY (ministry site unreachable, legislation portal refused access) | unset |
| UR-7 | Wage-protection (WPS) and payroll records | No period found | none | UNVERIFIED | unset |
| UR-8 | Commercial books under commercial law; free zones (DIFC, ADGM) | Not researched | none | UNVERIFIED | unset |
| UR-9 | Audit logs | No statutory period found | none | UNVERIFIED | Platform rule in section 9 |

### 3.3 Egypt
| ID | Category | Rule found | Source | Confidence | Platform default |
|---|---|---|---|---|---|
| ER-1 | Tax records, books and documents, including invoice copies | 5 years following the tax period covered by the declaration (Unified Tax Procedures Law 206 of 2020, Art. 38) | https://eg.andersen.com/wp-content/uploads/2025/09/Law-206-of-2020.pdf | TEXT (law-firm translation; 2025 amending laws not checked) | 5 years from period end |
| ER-2 | Commercial books and supporting documents; correspondence | 5 years from the closing annotation of the book; correspondence 5 years from dispatch or receipt (Trade Law 17 of 1999, Art. 26) | https://www.acerislaw.com/wp-content/uploads/2024/09/Commercial-Code-of-Egypt.pdf | TEXT (unofficial translation) | 5 years from book closure |
| ER-3 | E-invoices and e-receipts | Issued electronically; cancelled originals and copies must be kept (Art. 37); period read as ER-1 | Same as ER-1 | TEXT | As ER-1; cancelled documents never purged early |
| ER-4 | Employee files | 5 years after employment ends reported under Labour Law 14 of 2025; older summaries say 1 year | https://www.deloitte.com/middle-east/en/services/tax/perspectives/egypt-new-labor-law-entering-into-effect.html | SECONDARY, conflicting | unset |
| ER-5 | Payroll and social-insurance records | Not found | none | UNVERIFIED | unset |
| ER-6 | Audit logs | No statutory period found | none | UNVERIFIED | Platform rule in section 9 |

### 3.4 Qatar
Qatar is the planned first pilot market ([../architecture/phased-delivery-and-lanes.md](../architecture/phased-delivery-and-lanes.md)) and has no verified row. The official legal portal did not return article text to our tools.

| ID | Category | Rule found | Source | Confidence | Platform default |
|---|---|---|---|---|---|
| QR-1 | Accounting records for income tax | 10 years reported; the Income Tax Law (24 of 2018) has an article titled retention of accounting records, period not read | https://alansarilaw.com/?p=2542 | SECONDARY | unset |
| QR-2 | Commercial books | Commercial Law 27 of 2006 requires books (Arts. 21 to 23 as reported); retention period not found | none usable | UNVERIFIED | unset |
| QR-3 | VAT and e-invoicing records | No facts recorded (rows Q1, Q2 in [../compliance/country-matrix.md](../compliance/country-matrix.md)) | none | UNVERIFIED | unset |
| QR-4 | Payroll, wage-protection and employee records | No period found; one unsourced guide says 5 years; labour law reported amended in 2026 | none usable | UNVERIFIED | unset |
| QR-5 | Audit logs | No statutory period found | none | UNVERIFIED | Platform rule in section 9 |

## 4. Data-protection duties that shape deletion
| ID | Market | Rule found | Source | Confidence | Platform default |
|---|---|---|---|---|---|
| PK-1 | Saudi Arabia | No fixed retention period: personal data may be kept as long as needed for its purpose or as required by laws in force (regulator FAQ citing PDPL Art. 18) | https://dgp.sdaia.gov.sa/wps/portal/pdp/knowledgecenter | OFFICIAL (Arabic FAQ, machine-read; law text not read) | Purpose-bound retention; statutory records exempt from erasure |
| PK-2 | Saudi Arabia | The law reaches processing of residents' data by entities outside the Kingdom (FAQ citing Art. 2); a separate transfer regulation exists, content not read | Same | OFFICIAL for existence; transfer conditions UNVERIFIED | In-Kingdom hosting; model-provider transfers wait on LEG-012 |
| PK-3 | Saudi Arabia | Destroy when the purpose ends; may keep if anonymised or where a law or legal proceeding requires | law-firm summaries only | SECONDARY | Delete or anonymise at purpose end |
| PU-1 | UAE | Federal Decree-Law 45 of 2021: storage limitation, erasure, transfers | official portal refused access | UNVERIFIED | Same behaviour as PK-3 |
| PE-1 | Egypt | Law 151 of 2020 with executive regulations issued in 2025; a licence or permit is reported to be needed for transfers abroad; breach notice reported at 72 hours; a one-year compliance period is reported | https://www.tamimi.com/law_update_articles/from-policy-to-practice-egypt-issues-executive-regulations-of-the-personal-data-protection-law/ | SECONDARY | Same behaviour as PK-3; Egypt tenants hosted per DAT-003 |
| PE-2 | Egypt | Retention wording and processor licensing duties | none | UNVERIFIED | unset |
| PQ-1 | Qatar | Law 13 of 2016; regulator sits in the national cyber security agency; no official English text | https://www.dlapiperdataprotection.com/?c=QA&t=law | SECONDARY | Same behaviour as PK-3 |
| PQ-2 | Qatar | Retention, erasure and cross-border wording | none | UNVERIFIED | unset |

Platform behaviour in all four markets, pending counsel:
- **Minimise at collection.** Components declare which personal fields they need; optional fields are off by default.
- **Data-subject requests** go to the tenant (controller). The platform gives the tenant tools: find, export, correct, restrict, erase (no plan row yet; UNVERIFIED which rights each law grants).
- **Erasure meets statutory retention.** A personal field inside a record still under statutory retention (an issued e-invoice, a posted journal, a payslip) is not erased. It is restricted: hidden from search, chat, models and exports that are not statutory. It is erased or anonymised when the period ends.
- **Posted records are never edited to satisfy erasure.** Ledger and e-invoice immutability holds (AGENTS.md principle 3).

## 5. Legal hold
| Topic | Rule |
|---|---|
| What it is | A flag on a tenant, a record set, a person or a date range that stops every deletion and expiry job for the matched data, including backups and AI stores |
| Who sets it | Tenant owner (own data) or the platform's legal contact (dispute with a tenant, regulator or court request). Setting and lifting are R4 actions with a second approver ([action-policy-table.md](action-policy-table.md)) |
| Statutory extensions | Tax audit, dispute or voluntary disclosure (for example UR-3) are entered as holds with a reason code, not as edits to the pack period |
| Record | Who, why, scope, start, review date, lift; all in the audit log. A hold has a review date; it never expires silently |
| At offboarding | A tenant under hold can be exported and suspended but not deleted. The certificate is issued only after the hold lifts |
| Visibility | The hold's existence is visible to the tenant owner unless a lawful order forbids it (UNVERIFIED how each market treats this) |

## 6. Platform retention schedule by data category
Periods marked "pack" come from section 3 once confirmed. Periods marked "decision" have no statutory source and need a founder decision (section 12); no number is proposed here on purpose.

| Category | Class | Kept while tenant is active | After purpose ends or on request | Notes |
|---|---|---|---|---|
| Ledger, journals, tax and VAT records | C2 | Whole life of the tenant | Pack period, then eligible for purge only if the tenant asks | Never auto-purged for an active tenant (D-3) |
| Issued e-invoices and notes (signed XML, PDF) | C2 | Whole life | Pack period | Immutable archive |
| Payroll, payslips, wage-protection files | C3 | Whole life | Pack period; unset markets keep | |
| Employee records after the employee leaves | C3 | Pack period after exit | Then erase or anonymise | Leaver's national ID and bank account masked at exit, erased at period end |
| Job applicants not hired | C3 | Decision D-6 | Erase | No statutory source found |
| Customer and supplier contacts | C2 + PD | While the relationship or an open document needs them | Restrict if inside statutory records; else erase | |
| Blueprints and configuration history | C2 | Whole life (needed for audit and recovery) | Deleted with the tenant | |
| Uploaded source documents (discovery, imports) | Up to C3 | Decision D-7 | Erase after import is confirmed, unless attached to a statutory record | Raw flagged content: see Q-G in [prompt-injection-defence.md](prompt-injection-defence.md) |
| Brand assets | C2 or C0 | Whole life | Deleted with the tenant | |
| Audit log | C2 | Whole life | At least the longest pack period in the tenant's market (D-4) | Section 9 |
| Support tickets and session records | C2 | Decision D-8 | Erase | Access records themselves live in the audit log |
| Platform account and billing records about the tenant | C2 | Whole life | Our own statutory period as a company (UNVERIFIED, depends on LEG-010) | We are controller |
| Synthetic and demo data | C1 | No limit | n/a | |

## 7. Tenant offboarding, export and deletion
Lifecycle states come from PLT-004 (trial, active, suspended, exported, deleted). Every time limit below is a decision (D-1); [hosting-rules.md](hosting-rules.md) marks the SLAs as TBD and none is invented here.

| Step | What happens | Time limit |
|---|---|---|
| 1. Notice | Termination recorded; holds checked; tenant told what will be exported, deleted and kept | n/a |
| 2. Suspend | Sessions revoked, writes stopped, connectors and model calls disabled, scheduled filings stopped with a warning | Decision D-1 |
| 3. Export | Full export in an open format (DAT-006): ledger, documents, signed e-invoice archive, payroll, attachments, audit log, Blueprint. Short-lived link, owner only, audited. Engine internals and our keys are not exported | Decision D-1 |
| 4. Confirm | Tenant owner confirms receipt and integrity (hash manifest). Without confirmation the tenant stays in "exported" for the grace period | Decision D-1 |
| 5. Delete | Live site and database, storage prefix, search indexes, caches, memory, transcripts, embeddings and gateway logs removed; tenant keys scheduled for destruction | Decision D-1 |
| 6. Backups | Expire on schedule or are crypto-shredded (section 8) | Decision D-1 |
| 7. Verify and certify | Automated checks that no store answers for the tenant ID; certificate issued (DAT-007) | Decision D-1 |

- **Who keeps the statutory records after exit?** By default the tenant, using the export. The platform does not keep a copy "for the tenant's tax duty" unless the tenant buys an archive service (D-2). KR-3 and KR-6 matter here: Saudi records must stay reachable in the Kingdom, so the export must be storable there by the tenant.
- **Trials** that never went live hold no statutory records and are deleted after the trial grace period (D-1).
- **Sub-processors** (model providers, email, scanning) are told to delete, and their confirmation or their documented expiry is recorded in the certificate.

## 8. Backups, deletion propagation and crypto-shredding
| Topic | Rule |
|---|---|
| Expiry | Backups are per tenant, encrypted with that tenant's key, in the same country, and expire on a fixed schedule. The schedule is decision D-5; [hosting-rules.md](hosting-rules.md) says TBD |
| Backups are not archives | Statutory retention is met by live records and the immutable archive, never by old backups. So backup retention can be short |
| Propagation | A deletion or erasure in production reaches backups by expiry, not by editing backup files. The longest a deleted item can survive is the backup retention period; that figure is disclosed to tenants |
| Restore after deletion | A restore replays the deletion log before the system is opened, so erased personal data and deleted tenants do not come back |
| Crypto-shredding | Destroying a tenant's envelope keys makes every copy, including unexpired backups, unreadable. It is the default final step of tenant deletion, with a recovery window before key destruction (D-5). Requires that no tenant data is ever written under a shared key |
| Limits | Crypto-shredding is tenant-wide. It cannot erase one person. Single-person erasure uses the restrict-then-expire path. Whether regulators accept crypto-shredding as deletion is UNVERIFIED |
| Legal hold | Backup expiry and key destruction both stop for held tenants |

## 9. Audit logs, application logs and telemetry
| Store | Rule |
|---|---|
| Audit log (postings, approvals, configuration, AI actions, support access, deletion events) | Append-only and hash-chained (SEC-008). Kept for the life of the tenant, then at least as long as the longest statutory period in that market (D-4). Holds references and hashes, not C3 values, so it rarely needs erasure. Never edited; an erasure request is met by removing the lookup from user ID to name |
| Application logs, traces | No tenant content, no secrets, IDs only. Short fixed retention (D-9). Region-local |
| Security logs (authentication, access anomalies, tenant-boundary alerts) | Longer than application logs, for investigation (D-9) |
| Metrics, cost and usage telemetry | Aggregated per tenant; no personal data. Billing-relevant usage follows our own accounting retention |
| Web analytics on the marketing site | Minimal, consent-first; retention D-9 |

## 10. AI-specific retention
| Item | Rule |
|---|---|
| Prompts and model outputs logged by the gateway | Same class as the source data, per tenant, in region. Kept for a short fixed period for debugging and dispute handling, then deleted (D-10). OPR-012 implements |
| Chat transcripts shown to the user | Tenant data. Kept until the user or admin deletes or the tenant default expires them (D-10). A transcript is not the system of record: every action it caused is in the audit log |
| Evidence for an approval | The exact payload, its hash and the approver are kept in the audit log for the audit-log period, independent of transcript deletion |
| Per-tenant memory | Explicit entries with author, source and expiry; expire by default; listable and deletable by the tenant admin; deleted with the tenant ([../architecture/ai-layer.md](../architecture/ai-layer.md), OPR-014) |
| Embeddings, indexes, caches | Derived data: deleted or rebuilt whenever the source is deleted, erased or restricted; never outlive the source |
| Provider-side retention | A provider is approved only with written terms: no training on our or tenants' data, and zero retention or the shortest offered. Any abuse-monitoring retention is disclosed in the processor list and to tenants. No provider is chosen yet; no provider figure is asserted here (UNVERIFIED) |
| No zero-retention option | Then that provider gets C2 minimised data only, never C3, and the gap is a recorded risk |
| Evals and improvement | No production prompt, output or transcript enters an eval set. Only anonymised patterns promoted through DAT-008 |
| Model-drafted records | A draft never posted is ordinary C2 data and expires with its transcript. A posted record follows section 6 like any other |

## 11. What survives deletion, and why
| Kept | Content | Why |
|---|---|---|
| Deletion certificate | Tenant ID, scope, dates, store checklist, hash of the export manifest, sub-processor confirmations | Proof to the tenant and to a regulator that deletion happened |
| Tombstone | Tenant ID and deletion date, erased-subject pseudonymous ID | Stops a restore or a replay from resurrecting data |
| Our commercial records | Contract, invoices we issued, payments | Our own statutory duty as a company |
| Platform audit events about the tenant | Staff access, support sessions, the deletion events themselves; no tenant business content | Accountability for our own actions |
| Anonymised patterns already promoted | Output of DAT-008, class C1 | Not tenant data once anonymised under the contract clause; cannot be traced back |

Nothing else is kept. No "soft-deleted" tenant survives the grace period.

## 12. Decisions needed
| # | Decision | Note |
|---|---|---|
| D-1 | Offboarding time limits: suspension-to-export, export availability, grace period, deletion deadline, backup purge, trial grace | Needed for hosting-rules SLAs and the contract (LEG-013, LEG-015) |
| D-2 | Offer a paid read-only archive after exit, or export-and-delete only | Affects KSA in-Kingdom storage duty and pricing |
| D-3 | For an active tenant, purge statutory records past their period automatically, on request only, or never | Proposed: on request only |
| D-4 | Audit-log retention: longest statutory period in the market, or a single platform-wide figure | Proposed: per market, from the pack |
| D-5 | Backup retention period, and length of the recovery window before key destruction | Shorter is safer for deletion, riskier for recovery |
| D-6 | Retention for unsuccessful job applicants' data | No statutory source found |
| D-7 | How long raw uploaded discovery documents are kept after import | Ties to Q-G in the prompt-injection design |
| D-8 | Support ticket retention | |
| D-9 | Application-log, security-log and analytics retention periods | |
| D-10 | Gateway prompt and output log period; default transcript expiry; may a tenant set "no transcript history" | |
| D-11 | Ship a market with unset rows (keep everything, delete nothing automatically) or block launch until counsel confirms | Proposed: block the pilot on Qatar rows QR-1 to QR-4 and PQ-2 |
| D-12 | Is counsel's confirmation of sections 3 and 4 a phase-exit criterion for each market pack | Proposed: yes |

## 13. Open questions
1. Does any market put a record-keeping or data-return duty on the platform as processor after the contract ends?
2. Is crypto-shredding accepted as deletion under each market's data-protection law?
3. Does restriction instead of erasure for personal data inside statutory records satisfy each law, and for how long after the statutory period may it stay?
4. Which periods apply to payroll, wage-protection and employee files in each market (KR-8, UR-6, UR-7, ER-4, ER-5, QR-4)?
5. Must UAE e-invoice data be stored in the UAE (UR-5), and Egyptian or Qatari tax records in-country?
6. Do the 2025 Saudi VAT amendments, the 2026 UAE tax-procedures amendments or the 2025 Egyptian tax laws change KR-1 to KR-4, UR-1 to UR-3 or ER-1?
7. Is the Saudi Law of Commercial Books (KR-5) still in force as read, and does the longer of KR-1 and KR-5 govern invoices?
8. Do free-zone regimes (DIFC, ADGM, Qatar Financial Centre) need their own pack rows?
9. Are gateway logs of prompts a "record" a regulator can demand, and so subject to hold?
10. Can a tenant be told about a legal hold placed at an authority's request?
11. Breach-notification deadlines per market affect how long security logs must be kept; none is verified.
