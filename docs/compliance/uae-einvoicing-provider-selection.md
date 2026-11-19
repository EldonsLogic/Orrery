# UAE e-invoicing: accredited service provider selection (CMP-009)

Status: draft
Owner: eldon

Access date for every source: 2026-11-18. Confidence: VERIFIED means the primary source was read by the researcher; UNVERIFIED means not read, only reported, or only a vendor claim. Sources are the UAE Ministry of Finance (MoF) unless stated. This note chooses a process and a candidate pool; it endorses no provider. Companion files: [e-invoicing.md](e-invoicing.md), [country-matrix.md](country-matrix.md) (row U2, U3, U4), [vendor-certification.md](vendor-certification.md), [regulation-watch.md](regulation-watch.md), [../decisions/ADR-0024-four-phase-1-markets.md](../decisions/ADR-0024-four-phase-1-markets.md). No ADR on e-invoice vendor choice exists yet.

## 1. What the official sources say

| # | Fact | Source | Confidence |
|---|---|---|---|
| 1 | The model is called "Decentralized Continuous Transaction Control and Exchange (DCTCE)" with Corners 1 to 5; the supplier sends e-invoice data in PINT AE to its Accredited Service Provider (Corner 2). Unstructured PDF, Word, image, scan and email invoices are "not eInvoices". MoF page says it is the only official source | https://mof.gov.ae/en/about-us/initiatives/einvoicing/ | VERIFIED |
| 2 | The programme deck (Oct 2026) names the model "DCTCE / 5 corner" and says exchange between businesses is open: businesses can select and onboard an ASP; Corner 5 is "ready for Pilot Phase" (text partly extracted, slide images not read) | https://mof.gov.ae/wp-content/uploads/2026/10/UAE-eInvoicing-Programme-Oct2026.pdf | VERIFIED (partial) |
| 3 | Corner 5 is the tax authority corner (FTA): an e-invoice is one "reported electronically" to the FTA; the MoF page does not itself name Corner 5 as the FTA | same MoF page as 1 | VERIFIED (FTA = Corner 5 is an inference, see Q below) |
| 4 | The official ASP list shows 88 companies, each with an accreditation number, "Last updated on 18/11/2026 at 20:30", issued under Article 13 of Ministerial Decision (MD) 168 of 2026. The page has no per-provider status, API, sandbox or price field | https://mof.gov.ae/en/about-us/initiatives/einvoicing/einvoicing-accredited-service-providers-asps/ | VERIFIED |
| 5 | The e-invoicing page says ASP status "has been updated to Full Accreditation"; the programme deck (earlier, Oct 2026) listed 65 Accredited and 5 Pre-Approved providers. The list grows quickly; third-party counts differ | MoF page in 1; deck in 2 | VERIFIED (counts); trend UNVERIFIED |
| 6 | ASP accreditation conditions: active Peppol-certified provider that passed OpenPeppol conformance tests; at least two years operating an e-invoicing system; MD 168 Articles 6 to 11 (registration, obligations, tax registration, information security, self-declaration, insurance); ISO 22301 and ISO/IEC 27001 certificates; no fee; 90 working days. The page does not say whether a software vendor may become an ASP | https://mof.gov.ae/en/services/accreditation-of-einvoicing-service-providers/ | VERIFIED |
| 7 | MoF's ASP selection guide lists: tenure as a Peppol provider, UAE presence and accreditation date, own product vs reseller, direct support, value-added services and integration (ask about APIs, data formats), record retention and production to the FTA on request, security (encryption, access control, incident response), support and SLAs, pricing transparency, scalability. Per MD 168 of 2026, ASPs must give each end user 100 free e-invoice exchange and reporting services per year from signing the end-user agreement | https://mof.gov.ae/wp-content/uploads/2026/10/Considerations-for-selecting-an-Accredited-Service-Provider.pdf | VERIFIED (text extracted by script; headings partly lost) |
| 8 | Guidelines (taxpayer duties, from partial text): choose an ASP, complete contract and onboarding via EmaraTax, test with the ASP, keep details current with the ASP, report required tax data through it. Full read not completed (file would not load whole) | https://mof.gov.ae/wp-content/uploads/2026/10/UAE-Electronic-Invoicing-Guidelines_En.pdf | UNVERIFIED (partial) |
| 9 | PINT AE Billing v1.0.4 covers the Invoice and Credit Note transactions (semantic model, syntax binding, code lists, rules, Schematron). Status and authority not stated on the page | https://docs.peppol.eu/poac/ae/pint-ae/ | VERIFIED |
| 10 | MD 66 of 2026 amends Article 5(1)(a) of MD 244 of 2025 (Article text partly extracted; dates not read from the PDF) | https://mof.gov.ae/wp-content/uploads/2026/05/Ministerial-Resolution-No.-66-of-2026-Amending-Certain-Provisions-of-Ministerial-Resolution-No.-244-of-2025-Regarding-the-Implementation-of-the-Electronic-Invoicing-System-En-20260514.pdf | VERIFIED (title); dates UNVERIFIED |
| 11 | MoF news of 2026-05-10: for persons above AED 50 million annual revenue the ASP appointment deadline moved from 2026-07-31 to 2026-10-30; go-live "no later than 1 January 2027" unchanged. Also MD 64 of 2025 amended to allow technology solutions "in collaboration with third-party providers" | https://mof.gov.ae/en/news/ministry-of-finance-announces-targeted-amendments-to-einvoicing-system-decisions/ | VERIFIED |
| 12 | Legal instruments listed as current by MoF: MD 243 of 2025 (system), MD 244 of 2025 (implementation), MR 66 of 2026, MD 168 of 2026, MD 197 of 2026 (amends MD 243), Cabinet Decision 173 of 2026 (penalties). Repealed: Cabinet Decision 106 of 2025, Ministerial Resolution 56 of 2026, MD 64 of 2025 | MoF page in 1 | VERIFIED (listing only; decision texts not read) |

### Phase dates and conflicts
- AED 50m+ businesses: ASP by 2026-10-30, go-live 2027-01-01. VERIFIED (item 11). The 2026-10-30 date is already past on the access date.
- Businesses below AED 50m (ASP by 2027-03-31, go-live 2027-07-01) and government (ASP 2027-03-31, go-live 2027-10-01): reported by secondary sources only (country-matrix U2; search results quoting Baker McKenzie, a 2025 note that predates the amendments). Not confirmed on a primary page. UNVERIFIED. Do not tell customers these dates until MD 244 (as amended by MR 66, and MD 197 which amends MD 243) is read in full or counsel confirms.
- Conflicts seen: a vendor page (Comarch, https://www.comarch.com/trade-and-services/data-management/e-invoicing/) says "July 2026: mandatory for all transactions"; this conflicts with item 11 and with the pilot framing in item 2. Another vendor-style guide gives October 2026 as an effective date. Treat vendor date claims as UNVERIFIED. A press report names MD 243 instead of 244 for the May 2026 amendment (https://www.khaleejtimes.com/uae-amends-e-invoicing-regulations-to-reduce-operational-burden-on-businesses, search snippet only); the official MR 66 title says 244. B2C: secondary sources say excluded until further notice (UNVERIFIED).

## 2. Architecture

Taxpayer (our tenant) -> our ERP Runtime issues the invoice (Corner 1) -> tenant's chosen ASP (Corner 2) -> buyer's ASP (Corner 3) -> buyer (Corner 4); the ASPs report tax data to the FTA (Corner 5). This follows items 1 and 3; the exact reporting flow is to be read from the guidelines. The MoF documents place obligations on taxpayers (choose and onboard an ASP, keep details current) and on ASPs (Peppol, retention, security). No document read so far places a duty on an ERP vendor as such; MD 64 of 2025 as amended mentions technology solutions with third parties (item 11). Whether we need any status of our own is a counsel question (Q-210 below). Per ADR-0016, no customer-visible surface may name the engine.

| Layer | Build (our deterministic code) | Buy (provider) |
|---|---|---|
| Invoice and credit note data | Map ledger documents to PINT AE fields; validate against the published rules and Schematron; immutable after issue, corrections by credit note | none |
| Tax numbers and codes | VAT lines and totals from the tax engine in the UAE pack; never AI-written (AGENTS.md principle 3) | none |
| Serialisation | PINT AE XML generation in our code, golden-file tested | provider may re-validate |
| Participant identifiers, Peppol access, transmission, buyer-side delivery, reporting to the FTA | none (we do not become an access point in v1, e-invoicing.md) | ASP |
| Status and errors | Store provider status, show it in chat and the record, retries, audit log, dead-letter queue | provider returns acknowledgements and rejections |
| Inbound invoices | Parse PINT AE, three-way match, draft bills for human approval | provider delivers |
| Retention | Keep our copy per tax law | provider keeps its copy; confirm period (item 7) |

Integration pattern: one internal connector interface (`Connector` contract) with a per-provider adapter, so a second ASP can be added without changing the invoice component. Per principle 7, anything coming back from the ASP is untrusted data.

## 3. Candidate pool (primary evidence only)

The pool is the official list in item 4 (88 providers). A provider is a candidate only if on that list; every row below was accredited per MoF on 2026-11-18 (VERIFIED). Further columns come from the provider's own page fetched on 2026-11-18 and are vendor claims, UNVERIFIED as to truth; "not stated" means the page fetched did not say, not that the feature is absent. Only a sample of the 88 was read; the table is not a ranking.

| Provider (MoF accreditation no.) | Accreditation evidence | API availability | Arabic support | Pricing public? | Sandbox |
|---|---|---|---|---|---|
| A-Cube, Platform ACube Technologies LLC (188961) | MoF list, item 4 | Yes, "Emirates E-invoicing API"; Peppol format (https://acubeapi.com/en/uae) | not stated | not stated | Free test environment claimed on the same page |
| InvoiceQ For Information Technology Limited (114413) | MoF list | Yes, "secure APIs", 60+ system connectors claimed; "certified Peppol service provider" (https://ae.invoiceq.com) | Arabic site link; platform support not stated | Packages page linked, no prices seen | not stated |
| Defmacro Software DMCC (ClearTax) (163162) | MoF list | Claims unified API for 50+ mandates; no endpoint docs seen (https://www.cleartax.com/ae) | not stated | No; "Book a demo" | not stated |
| Comarch Middle East FZ LLC (110668) | MoF list | not stated (https://www.comarch.com/trade-and-services/data-management/e-invoicing/) | not stated | No public list; quoted by volume, countries, integration | not stated |
| Pagero Gulf FZ-LLC (153759) | MoF list; page redirects to a Thomson Reuters site, so not read | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| Other 83 on the list (examples: Avalara, Fonoa, Ecosio, EDICOM, SAP, Zoho, Tally, Wafeq, Qvalia) | MoF list | not read | not read | not read | not read |

## 4. Selection criteria (score from evidence, not from sales decks)

Must have (pass or fail): on the MoF list on the day of decision; written API documentation and a sandbox that exercises PINT AE and the FTA reporting leg; inbound and outbound; error and status codes returned per document; machine-readable webhooks or polling; contract allowing a multi-tenant reseller or embedded model (one ASP agreement per tenant is a design question, see Q-211); data location and DPA acceptable under the UAE PDPL position in data-protection-and-residency.md; ISO 27001 and ISO 22301 evidence (MoF requires them, item 6); documented exit and export of documents.

Weighted: Arabic UI, errors and support; public or at least written price per document and the 100 free documents rule (item 7); SLA and support hours; Peppol experience (MoF guide item 7); own product vs reseller (item 7); liability split and insurance; multi-country reach (KSA is a separate ZATCA channel, not Peppol); references from ERP embedders.

## 5. Recommended process (no endorsement before evidence)

1. Freeze the pool: re-download the MoF list on the day of work; keep the list date and accreditation numbers.
2. Screen all 88 on the must-have criteria using only public documentation; record URL and date per cell, mark "not stated" honestly.
3. Request written answers and sandbox access from a short list of three to five; use the same questionnaire for each.
4. Run a technical spike per candidate through the sandbox with synthetic data only: generate PINT AE, send, receive a rejection, receive an inbound.
5. Score, have a different model and a founder review, record an ADR (the decision becomes a new ADR; counsel input on Q-210 to Q-213 first).
6. Keep a second ASP as a documented fallback, behind the same adapter interface.

## 6. Risks
- Accreditation list moves daily (65 to 88 within weeks per items 2 and 4); status can change; re-check at contract and at go-live.
- Phase dates for businesses under AED 50m are not primary-confirmed (section 1); dates have changed more than once in 2026.
- Vendor documentation may sit behind logins and not be comparable; pricing is mostly private.
- An ASP contract may be per taxpayer, which affects how a platform onboards hundreds of tenants.
- The guidelines and the decision texts were not read in full here (PDF extraction was partial), so obligations on software vendors may be missed.
- Provider lock-in and liability for rejected or late reports.

## 7. Questions for counsel and the FTA
Logged in [../open-questions.md](../open-questions.md) as Q-210 to Q-213 (numbers are renumbered by the repo owner).

## 8. Sources
All URLs in sections 1 and 3 with access date 2026-11-18. Search aggregator pages were used only to locate primary pages; none is relied on for a VERIFIED row.
