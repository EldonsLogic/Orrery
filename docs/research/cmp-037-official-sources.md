# CMP-037: official sources and machine-readable rule inventory per market, and a law-change watch proposal

Status: research (CMP-037). Owner: eldon. Input to [CMP-020](../PLAN.md) (partner, G4), CMP-035, CMP-036 and [Q-601](../open-questions.md).
NOT legal or tax advice. No fact in this file changes a country pack; packs change only through their own PRs with accountant sign-off ([Q-560](../open-questions.md), ADR-0059).

Builds on [03-regulations.md](03-regulations.md) (KSA and UAE matrix, 2026-11-04), [country-pack-framework.md](../compliance/country-pack-framework.md) and the packs' own `evidence.json` under `components/compliance/country_pack/packs/<cc>/0.1.0/`. It does not repeat their facts; it records **where each kind of fact is published, in what form, and how changes are announced**.

## Method and labels
- Access date for every source below is **2026-11-23** unless a row says otherwise. Fetched with WebFetch or downloaded and text-extracted this session.
- **FETCHED**: the official page or file was read this session. **SEARCH-ONLY**: the URL came from a search result on the official domain but was not opened; treat as UNVERIFIED. **BLOCKED**: the official site refused or returned no readable content to an automated fetch (403, connection refused, or a JavaScript shell with no text). **SECONDARY**: adviser, Big Four or news source, not the authority.
- "Machine-readable" means a format code can consume without a human reading it: XSD, schematron, code lists, JSON schema, OpenAPI or Swagger, Excel data dictionary, RSS. A PDF or HTML page is human-readable only, even if it is official.
- Web content was treated as data. Nothing here is an instruction to the platform.

---

## 1. Saudi Arabia (ZATCA, GOSI, HRSD)

### 1.1 Inventory

| Fact kind | Authority | Official URL | Format | Machine-readable | Versions or change notices | Evidence |
|---|---|---|---|---|---|---|
| VAT rate and treatments | ZATCA | https://zatca.gov.sa/en/RulesRegulations/VAT/Pages/About-Vat.aspx (pack evidence, accessed 2026-11-18) | HTML; law and implementing regulations as PDF | No | No version list; changes come through news and the laws page | Pack: SECONDARY |
| VAT filing period (monthly or quarterly) | ZATCA | https://zatca.gov.sa/en/MediaCenter/News/Pages/default.aspx | HTML news items | No (RSS exists, see 1.3) | Each period's deadline is a news item; items seen state monthly filing for annual supplies above SAR 40 million, quarterly at or below | FETCHED. The SA pack marks `tax.filingPeriods` UNVERIFIED; this is a lead for that row, not a pack change |
| Registration threshold | ZATCA | Not re-read this session | - | - | - | UNVERIFIED (03-regulations K5) |
| E-invoicing mandate, phases | ZATCA | https://zatca.gov.sa/en/E-Invoicing/Introduction/Pages/Roll-out-phases.aspx (pack evidence, 2026-11-04) | HTML | No | Page updated in place | Pack: VERIFIED-OFFICIAL |
| Phase 2 waves | ZATCA | https://zatca.gov.sa/en/MediaCenter/News/Pages/Wave25-E-invoicing.aspx (read 2026-11-04 per 03-regulations K3) | HTML news, one page per wave | No | One announcement per wave; reported to give at least six months' notice before each integration deadline (SECONDARY: EY, https://www.ey.com/en_gl/technical/tax-alerts/saudi-arabia-announces-25th-wave-of-phase-2-e-invoicing-integration, not opened) | Wave 25 integration by 2027-02-01: SEARCH-ONLY this session |
| E-invoicing law and resolution | ZATCA | https://zatca.gov.sa/ar/E-Invoicing/Introduction/LawsAndRegulations/Documents/E-invoicing-Regulations.pdf and https://zatca.gov.sa/ar/E-Invoicing/Introduction/LawsAndRegulations/Documents/E-invoicing%20Resolution.pdf, listed on https://zatca.gov.sa/en/E-Invoicing/SystemsDevelopers/ComplianceEnablementToolbox/Pages/SupportingDocument.aspx | PDF | No | No version on the page; page "Last Update" 2026-08-10 | Listing FETCHED; PDFs not read |
| Invoice format and validation rules | ZATCA | https://zatca.gov.sa/en/E-Invoicing/SystemsDevelopers/Pages/E-Invoice-specifications.aspx lists the **XML Implementation Standard** (PDF) and the **E-Invoice Data Dictionary** (XLSX), both dated 2023-05-19, each in a final (`vF`) and a track-changes (`vTrack`) copy | PDF; XLSX | Data dictionary: yes (XLSX). Standard: no (PDF), but it carries the BR, BR-KSA and BR-KSA-DEC rule tables | Yes: dated file names plus a `vTrack` redline; page "Last Update" 2026-01-12 still lists the 2023-05-19 files | FETCHED (listing and the vF standard, version 1.2, 72 pages) |
| Executable validation (schematron, XSD) | ZATCA | SDK download page https://zatca.gov.sa/en/E-Invoicing/SystemsDevelopers/ComplianceEnablementToolbox/Pages/DownloadSDK.aspx (download needs accepting terms; served from a SharePoint link) | ZIP (SDK); PDF user manual | Yes, the SDK is what validates XML. Its contents (schematron and XSD files) were not inspected: UNVERIFIED | Page shows no version or changelog. The Developer Portal manual is reported to list an "SDK version history" (search snippet only) | FETCHED page; SDK not downloaded (licence terms need a human to accept) |
| Clearance and reporting API | ZATCA | Developer portal and sandbox https://sandbox.zatca.gov.sa/ (403 to our fetcher); manuals at https://zatca.gov.sa/en/E-Invoicing/Introduction/Guidelines/Documents/DEVELOPER-PORTAL-MANUAL.pdf and https://zatca.gov.sa/en/E-Invoicing/Introduction/Guidelines/Documents/E-invoicing-Detailed-Technical-Guideline.pdf | Web portal with Swagger (reported); PDF manuals | Swagger: yes if confirmed | Unknown | BLOCKED portal; manuals SEARCH-ONLY. Swagger and environments UNVERIFIED |
| Rounding | ZATCA | XML Implementation Standard v1.2, section 10 (see section 5, Q-601) | PDF | No (text); BR-CO rules enforced by the SDK | As above | FETCHED |
| Security (CSID, signing, QR) | ZATCA | https://zatca.gov.sa/en/E-Invoicing/SystemsDevelopers/Pages/Security-Requirements.aspx | HTML, PDF | No | Unknown | Listed on https://zatca.gov.sa/en/E-Invoicing/SystemsDevelopers/Pages/TechnicalRequirementsSpec.aspx (FETCHED); page itself not read |
| Social insurance (GOSI) | GOSI | https://www.gosi.gov.sa/en | JavaScript app | No content reached | Unknown | BLOCKED (empty shell to fetcher). Rates stay UNVERIFIED (03-regulations K12) |
| WPS (Mudad) | HRSD / Mudad | https://mudad.com.sa (pack evidence, not read) | Portal | Unknown | Unknown | UNVERIFIED |
| Labour law (hours, Ramadan, EOSB) | Bureau of Experts; HRSD | https://laws.boe.gov.sa | HTML, PDF | No | The law text is Arabic; the Arabic version governs (SECONDARY: WIPO Lex https://www.wipo.int/wipolex/en/legislation/details/14685, not opened) | BLOCKED (connection refused). Amendment history UNVERIFIED |
| Holidays and calendar | HRSD (private-sector holidays); Umm al-Qura calendar | No official source found this session | - | - | - | UNVERIFIED. Pending CMP-024 |

### 1.2 Coverage (what code can consume)
- **Automatic:** the SDK validation run (BR, BR-KSA, BR-KSA-DEC rules, signing and QR checks) against our generated XML; the E-Invoice Data Dictionary XLSX as a field list to diff between versions; Swagger, once someone with portal access confirms it exists.
- **Human plus accountant:** VAT rate and treatments, filing frequency, registration threshold, wave membership, retention, the e-invoicing resolution's legal text, GOSI rates, labour law, holidays. These are PDFs, HTML or news items and must be read and signed off.

### 1.3 Change signals
- ZATCA News has an RSS feed. The listing page links "View RSS feed" at `https://zatca.gov.sa/_layouts/15/feed.aspx?xsl=1&web=%2Fen%2FMediaCenter%2FNews&...`; the full URL was truncated in our fetch, so the exact feed URL is UNVERIFIED. A newsletter sign-up is at https://zatca.gov.sa/en/MediaCenter/NewsLetters/Pages/SubscribeNewsLetters.aspx (FETCHED as a link, not opened).
- E-invoice specifications change by publishing new dated files with a `vTrack` redline. The page's "Last Update" line moves when files change.
- The SDK has no public version list on the download page; the developer portal reportedly has one (UNVERIFIED).
- Frequency seen: waves are announced every few months (Wave 24 deadline 2026-06-30 (no source URL identified; UNVERIFIED), Wave 25 deadline 2027-02-01 (SECONDARY or SEARCH-ONLY)); VAT deadline news monthly; specs last changed 2023-05-19.

---

## 2. United Arab Emirates (MoF, FTA, MOHRE)

### 2.1 Inventory

| Fact kind | Authority | Official URL | Format | Machine-readable | Versions or change notices | Evidence |
|---|---|---|---|---|---|---|
| VAT rate, treatments, registration thresholds | FTA | https://tax.gov.ae/en/legislation.aspx (147 items, filter by tax, each with issue and publish date); guides and public clarifications https://tax.gov.ae/en/taxes/Vat/guides.references.aspx; archive https://tax.gov.ae/en/Legislation.archive.aspx | HTML listing, PDF documents | No | Issue and publish dates per item; no changelog, no RSS; titles say "and its amendments" | Listing FETCHED. Rates and thresholds not re-read: stay as in 03-regulations U5 |
| Federal laws (VAT law, labour law, PDPL) | Federal legislation portal | https://uaelegislation.gov.ae/en | HTML, PDF | Unknown | Unknown | BLOCKED (403) |
| E-invoicing mandate and phases | MoF | https://mof.gov.ae/en/about-us/initiatives/einvoicing/ (page footer "Last updated on 21/11/2026") | HTML; PDFs of decisions | No | The page keeps a "Repealed" list beside current legislation; no mailing list | FETCHED |
| E-invoicing legislation (current, as listed) | MoF; Cabinet | MD 243 of 2025; MD 244 of 2025; MR 66 of 2026 (amends 244); **MD 197 of 2026 (amends 243)**; MD 168 of 2026 (ASP accreditation); Cabinet Decision 173 of 2026 (penalties). PDFs under https://mof.gov.ae/wp-content/uploads/ linked from the page above | PDF | No | Repealed: Cabinet Decision 106 of 2025, MR 56 of 2026, MD 64 of 2025 | Listing FETCHED; PDFs not read. **MD 197 of 2026 and MD 168 / CD 173 of 2026 are not in the AE pack evidence**: flag for the AE pack owner |
| Mandatory fields | MoF | https://mof.gov.ae/wp-content/uploads/2026/10/UAE-Electronic-Invoice-Mandatory-Field-Requirements.pdf | PDF | No | Upload folder only, no version on page | Listed, not read |
| Guidelines | MoF | https://mof.gov.ae/wp-content/uploads/2026/10/UAE-Electronic-Invoicing-Guidelines_En.pdf | PDF | No | As above | Listed, not read |
| Invoice format and validation rules (PINT AE) | OpenPeppol (UAE Peppol Authority) | https://docs.peppol.eu/poac/ae/pint-ae/ : PINT AE Billing 1.0.4; schematron rules for invoice and credit note (`trn-invoice/rule/`, `trn-creditnote/rule/`), code lists, `resources.zip` | HTML spec; schematron; code lists; ZIP | **Yes** | Yes: release notes https://docs.peppol.eu/poac/ae/pint-ae/specialized-release-notes/ list 1.0.0 (2025-06-10), 1.0.1 (2025-07-31), 1.0.2 (2025-12-08), 1.0.2-hotfix (2026-01-28), 1.0.3-hotfix (2026-03-25), 1.0.4 (2026-06-02). No RSS or GitHub link on the page | FETCHED |
| Exchange API | ASP (Corner 2), not the state | ASP list https://mof.gov.ae/en/about-us/initiatives/einvoicing/einvoicing-accredited-service-providers-asps/ | HTML | No | Unknown | Linked, not read. Our integration is to the chosen ASP's API (CMP-009) |
| Rounding | FTA; PINT AE rules | No FTA rounding rule found. PINT AE schematron decimal and calculation rules not inspected | - | Schematron: yes | - | UNVERIFIED |
| WPS (SIF) | MOHRE | https://www.mohre.gov.ae | HTML | Unknown | Unknown | BLOCKED (connection refused). SIF spec UNVERIFIED |
| Holidays | Cabinet | https://u.ae/en/information-and-services/public-holidays-and-religious-affairs/public-holidays ("Updated on: 29 Oct 2026") cites Cabinet Resolution No. 27 of 2024 on public holidays; lists recurring dates, not year tables; Islamic dates depend on moon sighting | HTML | No | Page date only | FETCHED |

### 2.2 Coverage
- **Automatic:** PINT AE schematron and code lists (run them in CI against our generated UBL, pin the version); the release-notes page as a version signal. The ASP will also validate on its side.
- **Human plus accountant:** the MoF decisions and their amendments (dates, scope, B2C exclusion, penalties), the mandatory field PDF, FTA rates, thresholds and clarifications, WPS, holidays.

### 2.3 Change signals
- MoF e-invoicing page: edited in place, with a "Repealed" section and a footer date. Changed several times in 2026 (MR 56, MR 66, MD 168, MD 197, CD 173 all 2026). No feed; poll the page and diff the document list.
- PINT AE: about six releases in twelve months, including hotfixes. Poll the release notes.
- FTA legislation listing: issue and publish dates per item; poll and diff. No RSS was found on the page.

---

## 3. Egypt (ETA, NOSI)

### 3.1 Inventory

| Fact kind | Authority | Official URL | Format | Machine-readable | Versions or change notices | Evidence |
|---|---|---|---|---|---|---|
| VAT law and executive regulations | ETA | https://www.eta.gov.eg/en/content/value-added-tax-law; VAT executive instructions (Arabic) https://www.eta.gov.eg/ar/content/qwanyn-aldrybt-ly-alqymt-almdaft | HTML, PDF | No | No version list | Links FETCHED from https://www.eta.gov.eg/en/home; pages not opened. Rates stay as in the EG pack (UNVERIFIED) |
| Periodic instructions and circulars | ETA | https://www.eta.gov.eg/en/periodic-books-instruction/periodical-books | HTML, PDF | No | Dated items | Link FETCHED, page not opened |
| E-invoicing mandate (which taxpayers, by decision) | ETA | Guide https://www.eta.gov.eg/en/node/30; taxpayers-in-decisions inquiry `/einvoice-inquiry` on www.eta.gov.eg | HTML lookup | No | Mandates are by ministerial decision per taxpayer group | Links FETCHED; not opened. UNVERIFIED |
| Invoice format and document types | ETA | https://sdk.invoicing.eta.gov.eg/types/ : invoice, credit note, debit note at v0.9 and v1.0 (v0.9 has signature validation disabled); export invoice and notes at v1.0; e-receipt types at v1.2 (v1.0 and v1.1 retired) | HTML spec per document type, JSON and XML (stated in the pack evidence, not re-checked) | **No** (HTML documentation only; no JSON schema or XSD found; documentation pending executable artifacts) | Yes, versioned document types with retirement | FETCHED |
| Code tables | ETA | https://sdk.invoicing.eta.gov.eg/codes/ | HTML tables | No (HTML tables; no download confirmed; documentation pending executable artifacts) | Unknown | Linked, not opened |
| Invoicing and receipt API | ETA | https://sdk.invoicing.eta.gov.eg/api/ , `/einvoicingapi/`, `/ereceiptapi/`, `/apigovernance/` on the same host | HTML API reference | No (HTML documentation only; no OpenAPI or Swagger file found; documentation pending executable artifacts) | Yes, see release notes | Linked from https://sdk.invoicing.eta.gov.eg/start/ (FETCHED). Environment base URLs not on the start page: UNVERIFIED |
| Rounding | ETA | Not found | - | - | - | UNVERIFIED |
| Social insurance | NOSI | Official site not found by search | - | - | - | UNVERIFIED. Law 148 of 2019 amended by Law 8 of 2024 (SECONDARY: ILO NATLEX https://natlex.ilo.org/dyn/natlex2/r/natlex/fe/details?p3_isn=115545, not opened) |
| Holidays | Cabinet / Prime Minister decisions | Not found | - | - | - | UNVERIFIED |

### 3.2 Coverage
- **Automatic:** none confirmed. The ETA document types, code tables and API reference are HTML documentation pending executable artifacts (XSD, JSON schema, OpenAPI or a downloadable code list); until one is found they need a human reading. The release-notes page is a version signal only.
- **Human plus accountant:** VAT law and instructions (mostly Arabic PDFs), which taxpayers are mandated, social insurance, holidays.

### 3.3 Change signals
- SDK release notes https://sdk.invoicing.eta.gov.eg/release-notes/ : monthly releases from Nov 2020 to Aug 2023 (latest listed "Aug 2023 Release", 2023-08-22); none listed after that. Either the SDK is stable or notes moved: UNVERIFIED. Dates on the page mix DD-MM and MM-DD formats.
- ETA home has an email registration heading but no form reached, and no RSS. News at https://www.eta.gov.eg/en/news.

---

## 4. Qatar (GTA, MoF, MoL)

### 4.1 Inventory

| Fact kind | Authority | Official URL | Format | Machine-readable | Versions or change notices | Evidence |
|---|---|---|---|---|---|---|
| Taxes in force (VAT not found) | GTA | https://www.gta.gov.qa/en lists global minimum tax, income tax, capital gains tax, withholding tax and excise tax; VAT not found on this page; UNVERIFIED | HTML | No | - | FETCHED (one page only). The QA pack verifies only that VAT is absent from this page; Qatar's VAT legal status is UNVERIFIED |
| Tax laws, decisions, circulars | GTA | https://gta.gov.qa/en/laws ; https://gta.gov.qa/en/decisions ; https://gta.gov.qa/en/circulars | HTML, PDF | No | Dated items (not opened) | Links FETCHED |
| E-invoicing law | MoF with GTA | No official text found. Cabinet approved a draft law and executive regulations on 2026-05-06 (SECONDARY: EY https://www.ey.com/en_gl/technical/tax-alerts/qatar-approves-draft-e-invoicing-law-and-implementing-regulations, cited in the QA pack, accessed 2026-11-18) | - | - | Will appear in the Official Gazette (Al Meezan) once issued | UNVERIFIED; not promulgated as far as found |
| Legislation portal and gazette | Ministry of Justice | https://www.almeezan.qa/ | JavaScript app | No content reached | Unknown | BLOCKED |
| Tax portal | GTA | https://dhareeba.gov.qa | Portal | No | - | Link FETCHED |
| WPS | MoL with Qatar Central Bank | MoL site not reached. Minister of Labour Decision No. 50 of 2026 amends Decision No. 4 of 2015 on WPS, published in the Official Gazette on 2026-09-07 (SECONDARY: EY https://taxnews.ey.com/news/2026-2050-qatar-amends-wage-protection-system-salary-payment-deadlines-effective-8-september-2026, not opened). SIF guides are published by banks (SECONDARY) | - | - | Gazette | UNVERIFIED. Not in the QA pack evidence: flag for G3 payroll |
| Holidays | MoL / Amiri Diwan | Announced per holiday by news (QA pack cites The Peninsula, SECONDARY) | HTML news | No | Per announcement | UNVERIFIED |

### 4.2 Coverage
- **Automatic:** nothing today. No e-invoicing spec found; UNVERIFIED.
- **Human plus accountant:** all of it. The watch matters most here: the e-invoicing law and its technical spec are the next big change.

### 4.3 Change signals
- GTA news https://gta.gov.qa/en/media-center/news and notifications https://gta.gov.qa/en/media-center/notifications : several items a month (latest seen 2026-11-17; none on e-invoicing or VAT). Newsletter sign-up offered without a URL; no RSS.
- Official Gazette via Al Meezan (blocked to automated fetch).

---

## 5. Q-601 input: does ZATCA mandate rounding?

**Finding (official, FETCHED 2026-11-23):** ZATCA, *Electronic Invoice XML Implementation Standard*, version 1.2, dated 2023-05-19, https://zatca.gov.sa/ar/E-Invoicing/SystemsDevelopers/Documents/20230519_ZATCA_Electronic_Invoice_XML_Implementation_Standard_%20vF.pdf , **section 10 "Rounding" (page 29 of 72)** says rounding "shall be performed by using 'half-up' rounding", with examples to two and four decimals, and three rules:
1. document-level totals are rounded to two decimals;
2. rounding is done on final calculation results, not intermediate results;
3. the VAT category tax amount (BT-110) is rounded at document level, not summed from rounded line VAT amounts.

Related rules in the same standard: BR-CO-17 and the standard-rated VAT breakdown rule require the category tax amount to equal taxable amount times rate, "rounded to two decimals" (pages 39 to 40); the BR-DEC and BR-KSA-DEC tables (sections 13.2.8 and 13.3.2) cap decimals per field. The invoice line net amount section (page 17) says the parts of that calculation "must be rounded separately", which reads against rule 2 above.

**Open points for the accountant (UNVERIFIED):**
- Legal force: the standard is ZATCA's technical standard to the E-Invoicing resolution; whether it binds the ledger or only the e-invoice XML is a legal reading.
- Negative amounts: "half-up" is defined only by positive examples. The SA pack's `half_away_from_zero` gives the same result for positive values; whether credit notes ever carry negative amounts to round was not checked.
- The tension between page 17 (round the parts separately) and section 10 (round final results only).
- Whether the 2023-05-19 file is still the current one: the specifications page (last update 2026-01-12) lists no newer file.

This is input only. Q-601 stays open; the accountant decides whether `tax.roundingRule` is a statutory value for Saudi Arabia (CMP-036 product-choice list).

---

## 6. Cross-market summary

| Market | Machine-readable rule source | Version signal | Human-only core |
|---|---|---|---|
| SA | SDK (validation), Data Dictionary XLSX, Swagger (UNVERIFIED) | Dated spec files with redlines; news RSS (URL UNVERIFIED) | VAT, waves, retention, GOSI, labour law, holidays |
| AE | PINT AE schematron and code lists | PINT AE release notes; MoF page document list and footer date | MoF decisions, FTA rates and clarifications, WPS, holidays |
| EG | None confirmed (ETA HTML documentation pending executable artifacts) | SDK release notes (none after 2023-08) | VAT law, mandate decisions, social insurance, holidays |
| QA | None found; UNVERIFIED | GTA news; Official Gazette | Everything, including the e-invoicing law (status UNVERIFIED) |

Gaps to close (each needs a human with a browser or portal access): ZATCA developer portal and SDK contents; uaelegislation.gov.ae, mohre.gov.ae, laws.boe.gov.sa, gosi.gov.sa and almeezan.qa blocked our fetcher; NOSI official site not found; no official holiday source for SA, EG or QA.

---

## 7. Proposal: law-change watch (input to CMP-020, partner, G4; nothing is built here)

**Goal.** Notice when an official source changes, tie the change to the pack facts it could affect, and put those packs into review. The watch never edits a fact (principle 3). Its output is a review ticket, not a pack change.

### 7.1 What to poll
A **source registry** (one entry per URL in sections 1 to 4) with: `id`, `market`, `authority`, `url`, `kind` (`html`, `pdf`, `rss`, `schematron`, `codelist`, `api-spec`, `sdk`), `pollEvery`, `extract` (how to normalise: whole file hash, document-list diff, release-notes list), and `affects` (the pack paths, as in `evidence.json` `paths`, that this source backs). The registry is the join between a source and the `evidence.json` facts that cite it, so it can be checked by script: every `sources[].url` in a pack should map to a registry entry or be listed as unwatched.

| Source class | Examples | Poll | Change test |
|---|---|---|---|
| Executable specs | PINT AE release notes and `resources.zip`; ZATCA SDK; ETA document types (documentation only, pending executable artifacts) | Daily | New version id, or file hash change |
| Spec listings | ZATCA E-Invoice specifications page; MoF e-invoicing page | Daily | New or removed document link; footer date change |
| Legislation listings | FTA legislation; GTA laws, decisions, circulars; ETA periodical books | Daily | New item (issue and publish date) |
| News feeds | ZATCA News RSS; GTA news; MoF news; ETA news | Every few hours | New item whose title or body matches a market keyword list (e-invoicing, VAT, wave, threshold, rate, WPS, holiday) |
| Gazettes and portals that block bots | Al Meezan, uaelegislation, BOE, MOHRE, GOSI | Weekly, by a person | Manual check recorded in the log |

Respect each site's terms and robots rules; no logins, no portal scraping behind authentication, no captcha bypass. Store fetched copies outside the repo (repo hygiene forbids PDFs and downloads), keeping only hashes and URLs.

### 7.2 From change to pack review
1. **Detect.** A poll finds a change and writes a `source-change` event (source id, old and new hash or version, diff summary, fetched at).
2. **Summarise.** A small-tier model may write a plain summary of the diff and suggest which `affects` paths it touches. The summary is labelled UNVERIFIED and carries no value for any fact. It never writes rates, thresholds, dates or rounding.
3. **Flag.** Each affected pack version gets a `review-required` flag naming the source change. For executable specs, CI also runs the new schematron or SDK against our test invoices and attaches the result: a failing rule is a fact, not a model opinion.
4. **Gate.** While a pack has an open `review-required` flag on a locked path, it is treated like an open `goLiveBlockers` entry: production keeps the last certified version and refuses to certify a new one (consistent with CMP-036). Existing tenants stay pinned; nothing auto-upgrades.
5. **Decide.** A person reads the official source, updates `evidence.json` and `pack.json` in a pack PR (patch, minor or major per the framework's versioning rules), and records the outcome on the flag: changed, no impact, or not applicable, with who and when.
6. **Sign off.** Per Q-560 and ADR-0059: the named accountant for that market signs off and one founder approves before the new version is `certified`. Schematron or SDK upgrades go through the rigid-zone review of the component they belong to.

### 7.3 Who owns what
- CMP-020 owner (partner): the watcher service and registry format.
- Pack owners: the `affects` mapping for their pack and the review of each flag.
- Market accountant: sign-off on any changed statutory fact.
- Founders: one approval per certified version; decide when a source with no feed needs a manual weekly check.

### 7.4 Open design questions for CMP-020
- Where the registry lives (beside each pack, or one file per market under `components/compliance/`), and whether `check_country_packs` should require every source to be watched.
- How to treat a source that disappears (404): flag, not silent.
- Whether to subscribe a shared mailbox to ZATCA and GTA newsletters, and who reads it.
- How fast a flag must be cleared before a mandated deadline (for example a ZATCA wave) becomes a go-live risk.

## Sources
All official URLs are in the tables, accessed 2026-11-23 unless labelled otherwise. SECONDARY sources used: EY tax alerts (Saudi Wave 25; Qatar e-invoicing draft law; Qatar WPS Decision 50 of 2026), ILO NATLEX (Egypt Law 148 of 2019 amendments), WIPO Lex (Saudi Labour Law). Search result summaries that were not opened are marked SEARCH-ONLY and count as UNVERIFIED.
