# Egypt go-to-market assessment (GTM-017)

Status: draft
Owner: eldon

Egypt is a phase-1 market with no fixed launch order ([ADR-0024](../decisions/ADR-0024-four-phase-1-markets.md)). This is a desk assessment, not a decision. Access date for every source: 2026-11-19. Labels: **VERIFIED** = primary page read in full on the access date; **UNVERIFIED** = search snippet, vendor, press or secondary source (the primary page was not read, or the fetch failed). Short paraphrases only. Regulation facts come from [../compliance/egypt-research.md](../compliance/egypt-research.md) (CMP-027), where only the ETA SDK pages are VERIFIED. Not legal, tax or investment advice. No pricing figures and no dates for our own plans appear here; price hypotheses stay in [../strategy/07-pricing.md](../strategy/07-pricing.md).

## 1. Bottom line
- Demand signal is real but unquantified for our band: the e-invoice mandate is live and tied to a small-business tax regime, but we have no verified count of 10-100 staff firms and no interview evidence from Egyptian owners.
- The biggest blockers are not demand: the data-protection permit question (section 6), per-tenant e-invoice signing custody (section 5) and currency risk (section 4).
- Recommendation: GO for research and 8 to 10 Egyptian interviews now; NO-GO for building the Egypt pack beyond CMP-028 research until the criteria in section 11 are met.

## 2. Market size and segmentation
| # | Finding | Source | Label |
|---|---|---|---|
| 2.1 | The CAPMAS 2017 economic census counted about 3.7 million active establishments; about 99.7% had fewer than 50 staff and about 91.7% were micro. | https://www.oecd.org/en/publications/sme-and-entrepreneurship-policy-in-egypt_195d9c43-en/full-report/sme-and-entrepreneurship-performance-and-characteristics-in-egypt_a963c2a5.html (OECD page returned HTTP 403 to our fetch; figure seen in search summary) | UNVERIFIED |
| 2.2 | Same source's shares: about 89% under 5 staff, 8% with 5-9, 2% with 10-19, 0.7% with 20-49. So our 10-49 band is about 2.7% of establishments, roughly 100,000 firms by our arithmetic on 3.7 million (ESTIMATE, 2017 base, includes unregistered firms). Band 50-100 not separated. | same | UNVERIFIED |
| 2.3 | A press item cites CAPMAS for about 3.65 million MSMEs employing 9.7 million people (2020 figure, unit ambiguous). | https://www.egypttoday.com/Article/3/85024/Total-output-of-Egypt-s-MSMEs-hits-LE-1-2T | UNVERIFIED |
| 2.4 | MSME Law 152 of 2020 defines size by annual turnover (and capital for new industrial firms), not by staff count; amendments reported with conflicting new thresholds; unclear which are in force. MSMEDA is the state agency. | https://eg.andersen.com/wp-content/uploads/2026/06/Law-No.-152-of-2020.pdf ; https://en.amwalalghad.com/?p=225404 | UNVERIFIED |
| 2.5 | The CAPMAS census portal holds the 2017/18 employee-size tables (primary source to read next). | https://censusinfo.capmas.gov.eg/Metadata-en-v4.2/index.php/catalog/405/download/842 | UNVERIFIED (not read) |

Reading: most firms are micro and informal; our 10-100 staff owner-led band is a thin slice, and the share that is formal, VAT-registered and sells on credit is smaller still. SAM cannot be stated without the census tables and ETA taxpayer counts. Sector split (trade, manufacturing, services) not obtained.

## 3. Software adoption, ERP incumbents and substitutes
No independent SME ERP adoption rate was found. Market-size pages found were vendor or research-house marketing (one reports a USD billion figure for cloud ERP for SMEs, method unknown; not used here).

| Competitor or substitute | Type | What we know | Source | Label |
|---|---|---|---|---|
| Odoo via local partners | Global open-source ERP, local implementers | Many Egyptian partner sites; partner marketing claims full ETA, VAT and Arabic localisation. Self-interested claim. | https://ecosire.com/blog/odoo-erp-egypt-business-guide ; https://www.ksolves.com/blog/odoo/odoo-implementation-partner-in-egypt | UNVERIFIED |
| SAP (Business One / ByDesign), Microsoft Dynamics, Oracle, Infor | Global, partner-sold | Named as present in Egypt by research-house profiles; no share, price or SME fit data. | https://www.nextmsc.com/compass/egypt/erp-software-market | UNVERIFIED |
| Daftra | Local-regional cloud accounting and invoicing | Says it integrates with ETA e-invoicing and has over 10,000 SMEs (vendor claim). | https://daftra.com/en/egy-electronic-invoice | UNVERIFIED |
| Wafeq | Regional cloud accounting | Reported Egypt expansion; has an Egypt page. | https://www.wafeq.com/en-eg/success-stories/wafeq-client-stories:-scope-solutions-or-cloud-transformation-for-smes | UNVERIFIED |
| Zoho, Qoyod, Frappe/ERPNext partners | Cloud accounting or ERP | No usable Egypt-specific evidence found; test in interviews. | n/a | research needed |
| Spreadsheets, desktop accounting, manual ledgers plus outsourced accountant | Substitute | Vendors state many SMEs relied on ledgers or spreadsheets before the ETA push. | https://aviaanaccounting.com/accounting-services-in-egypt/ | UNVERIFIED |
| Bookkeeping and outsourcing firms | Substitute and channel | Many firms market bookkeeping to SMEs; Egyptian accountants with Odoo skills listed on freelance sites at low hourly rates (price pressure on implementation). | https://aviaanaccounting.com/bookkeeping-firms-in-egypt/ ; https://www.upwork.com/hire/financial-accountants/eg/ | UNVERIFIED |
| Local ERP houses (names to collect) | Local vendors | Not yet identified from evidence; list in interviews. | n/a | research needed |

Implication: the field is crowded at the cheap end (cloud invoicing, Odoo partners) and our gap hypothesis (chat-built, configuration-only ERP with compliance built in) is unproven here. The cost-of-implementation argument may be weaker than in the Gulf if local implementer labour is cheap.

## 4. Accountants, channel, payment and pricing norms
- Channel: accountants and tax advisers are the likely shortlist influencers (hypothesis from [README.md](README.md), UNVERIFIED for Egypt). The e-invoice mandate gives them a reason to recommend tools; it also gives them a veto if we look like a replacement. Interview 5 or more.
- Implementer partners exist in volume (Odoo); a "platform partner" model competes with them for the same projects.
- Payments: instant bank rails exist (InstaPay, with reported per-transaction limit of EGP 70,000 and daily limit of EGP 120,000) and Fawry runs a business platform; a national bank launched a B2B payment service. Vendor and press sources. https://www.lightspark.com/knowledge/egypt-instant-payments ; https://english.ahram.org.eg/News/540315.aspx ; https://pymnts.com/?p=1196524 (all UNVERIFIED). Cheque use and typical B2B credit terms: not found, research needed.
- Currency: reports in 2026 put the pound roughly between 49 and 56 per US dollar, with a sharp fall in March and April; one headline reports above 56 at banks (undated); policy rate reported 19% deposit and 20% lending on 2026-04-02; headline inflation 13.4% in February 2026. https://english.ahram.org.eg/News/563600.aspx ; https://english.ahram.org.eg/News/580952.aspx (UNVERIFIED; check the Central Bank of Egypt site).
- Pricing risk: USD-denominated subscriptions would swing with the pound and raise churn and collection risk; EGP-denominated prices would erode our margin in dollar costs (AI calls, hosting). Needs a currency policy decision (question F3). Whether foreign-currency invoicing is allowed is open (CMP-027 table, question 11).
- Buying power: a cheaper local cost base and lower willingness to pay than in the Gulf is a hypothesis; the 25-interview price ladder in [README.md](README.md) is in SAR and must be re-based for Egypt.

## 5. E-invoice and e-receipt as the forcing function
From the VERIFIED ETA SDK pages ([egypt-research.md](../compliance/egypt-research.md) 1.1 to 1.4): ETA runs an eInvoicing and eReceipt system; each taxpayer registers its ERP or POS system and gets credentials; documents are signed with an eSeal X.509 certificate using CAdES-BES over a SHA-256 hash; a PreProd test environment exists. Source https://sdk.invoicing.eta.gov.eg/ (read again today: documents the APIs for taxpayer ERP and POS systems; page last updated 2022-12-08; states no phases or who is obliged) - VERIFIED.

Not verified (UNVERIFIED, secondary): the obligation phases and dates (conflicting, CMP-027 1.5 to 1.7); that e-invoice and e-receipt compliance is a condition for the small-business simplified tax regime of Law 6 of 2025 (turnover up to EGP 20 million), reported by press quoting the ETA head, https://www.zawya.com/en/economy/north-africa/e-invoice-e-receipt-compliance-required-to-benefit-from-simplified-tax-system-egypts-eta-head-b4r659j9 ; reports that e-receipt scope is by named taxpayer lists in 2025 decisions (281 and 361) and that the VAT threshold may have fallen from EGP 500,000 to EGP 250,000 (single secondary source, conflicts with CMP-027 2.1), https://invoicedataextraction.com/blog/egypt-electronic-receipt-compliance-guide ; https://vatit.com/e-invoicing-guide/egypt/.

Effect on GTM:
- If the mandate reaches all VAT-registered firms (to be confirmed), the forcing function is strong, but cheap invoicing tools (section 3) already serve it. We win only if the owner wants the whole business on one system, not just invoices.
- Per-tenant registration and eSeal custody (CMP-027 counsel question 3, and 4 on solution-provider approval) decide whether a hosted, self-serve onboarding is possible. Until answered, onboarding is assisted.
- A "readiness checker" for the Egyptian obligated-taxpayer lookup can be an inbound hook only after the lookup is read on the ETA site.

## 6. Data protection, hosting and AI calls (all UNVERIFIED)
Per CMP-027 section 3, secondary sources report: Law 151 of 2020 with executive regulations issued 2025-11-01 and a one-year compliance period; a Personal Data Protection Centre issuing licences and cross-border transfer permits; a DPO duty; 72-hour breach notice. Sources: https://cms.law/en/are/legal-updates/egypt-s-pdpl-executive-regulations-issued-one-year-compliance-countdown-begins and https://www.legal500.com/guides/hot-topic/strategic-challenges-and-opportunities-in-cross-border-data-transfers-under-egypts-personal-data-protection-regime. One search result said 45% of SMEs worry about data security and compliance (vendor report, sample unknown; https://www.kenresearch.com/egypt-cloud-erp-for-smes-market, UNVERIFIED).

Effect, if the permit reading holds: hosting outside Egypt and any foreign model API call carrying personal data may need a permit, which could stop a launch or force in-country hosting and a routed model. In-country cloud regions are not researched (country-matrix E8). Interim rule stays: no real Egyptian customer data until counsel answers ([../compliance/data-protection-and-residency.md](../compliance/data-protection-and-residency.md)). Synthetic demos are unaffected.

## 7. Language and dialect
- No survey of Egyptian business users on Arabic versus English interfaces, or Modern Standard versus Egyptian dialect, was found (search returned only anecdotes and a forum thread about missing Arabic in a global product). UNVERIFIED.
- Working hypothesis: owners speak Egyptian Arabic and write business documents in Arabic or English; the interface can stay Modern Standard Arabic ([../brand/06-voice-tone.md](../brand/06-voice-tone.md) is Gulf-friendly MSA), but the chat interview must understand Egyptian dialect and mixed Arabic-English. Test with 5 recorded dialect sessions before promising it. The discovery model's dialect quality is an eval item, not an assumption.
- Invoice language rule not researched (CMP-027 5.3).

## 8. ICP hypotheses and niche template
| ICP | Profile | Why | Template fit | Evidence needed |
|---|---|---|---|---|
| A (lead) | Trading and distribution, 10-100 staff, VAT-registered, 1-5 branches, sells on credit, cheque and bank-transfer collections | Matches the first template ([../strategy/02-niche-and-launch-country.md](../strategy/02-niche-and-launch-country.md)); high invoice volume under e-invoicing | Trading and distribution template | Interviews: current tool, pain, willingness to pay in EGP |
| B | Light manufacturers and food producers, 20-100 staff | Large manufacturing share in Egyptian SMEs (UNVERIFIED, not sourced) | Needs BOM and costing depth; not in seed | Sector count; component gap review |
| C | Service firms with payroll-heavy staff (contractors, facility management) | Labour Law 14 of 2025 and insurance rates add pain (CMP-027 section 4, UNVERIFIED) | Payroll component is weak in the seed | Payroll formats verified |
| Rejected for now | Retail and F&B point of sale, clinics | POS-first and regulated; e-receipt integration scope open (CMP-027 1.6) | none | n/a |

Pick A for Egypt interviews because it reuses the lead template; confirm or drop after interviews.

## 9. Entry shape
| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Direct, founder-led, assisted onboarding | Fast learning; fits the unverified signing and permit questions | Does not scale; no local presence or entity | Start here, a handful of design-partner tenants on synthetic then real data once counsel clears |
| Accountant-led partner (accountants resell and run the books) | Trusted channel; fits Egyptian filing duties; may unlock many small clients | Veto risk; partner pulls us toward software-house work | Test in interviews; pilot with 2 firms before a programme |
| Implementer partners (Odoo-style) | Existing delivery capacity | Competes with their product; cheap labour | Only as discovery and training partners |
| Marketplaces, paid ads, cold outbound | None here | Rejected in [README.md](README.md) | No |

Entity and contracting rules for Egypt are open (CMP-027 question 12; LEG-003, LEG-010).

## 10. Risks
1. Permit or hosting rule blocks foreign hosting and foreign AI calls (section 6).
2. E-invoice scope and dates unclear; signing custody may force per-tenant tokens (section 5).
3. Pound volatility hits pricing and margins (section 4).
4. Crowded cheap segment (Daftra-type tools, Odoo partners) and cheap local implementation labour.
5. Informality: many target firms may not be formal or on credit terms, shrinking the band.
6. Accountant veto or lock-in by incumbents.
7. Frequent tax and payroll rule changes (CMP-027 section 7).
8. Dialect and Arabic quality in the chat interview.
9. Evidence is almost all secondary; nothing in this file is decision grade yet.

## 11. Go and no-go criteria
| # | Criterion | Go if | No-go or change if | Evidence that would change the view |
|---|---|---|---|---|
| 1 | Pain and willingness to pay | 8 of 10 Egyptian owners describe a current ERP or e-invoice pain they would pay to fix; 5 would pay a stated EGP-denominated price | Fewer than 5 describe the pain | Interview log (reuses the 25-interview plan, Egypt slice) |
| 2 | Accountant stance | Fewer than half of accountants veto or oppose | More than half | Seven accountant interviews |
| 3 | Mandate scope | ETA primary text confirms the band is obliged and enforced | Small firms exempt or enforcement lax | ETA decisions and obligated-taxpayer lookup read; counsel answer |
| 4 | Signing and registration | Hosted signing or assisted per-tenant eSeal is allowed and practical | Each tenant needs a token we cannot manage | Counsel question 3 and 4; PreProd spike |
| 5 | Data protection | Counsel confirms a workable path (in-country hosting or a granted permit) | Permit infeasible and no in-country option for hosting and model calls | Counsel question 5 and 6; in-country region check |
| 6 | Currency | A pricing and collection policy that survives a 20% move | Only USD or only EGP works and both fail | Founder decision; interviews on currency preference |
| 7 | Market band | Census and ETA counts show a band large enough for the plan | Band too small or mostly informal | CAPMAS tables; ETA taxpayer counts |
| 8 | Competition | Interviewees name gaps in Daftra, Odoo-partner and local ERP offers | Owners satisfied with cheap tools | Interview comparison questions |
| 9 | Language | Dialect eval passes on recorded Egyptian sessions | Fails and cannot be fixed | Eval run |

## 12. Questions for the founders
F1. Do we run Egyptian interviews now, and who owns sourcing (founders' networks in Egypt)?
F2. Is Egypt ahead of or behind Qatar for the first live market, given ADR-0024 says readiness decides?
F3. Currency policy for Egyptian tenants: priced in EGP, USD or both, and who carries the exchange risk?
F4. Do we accept assisted onboarding and no self-serve in Egypt at first?
F5. Is an accountant-led pilot acceptable if it means sharing revenue?
F6. Do we have contacts for a local entity, bank and accountant for LEG-003 and LEG-010?

## 13. Questions for local advisers (adds to CMP-027 section 8)
L1. Which firms in our band must issue e-invoices and e-receipts today, and what is enforced (checks, fines)?
L2. Is the small-business simplified regime tied to e-invoicing, and which turnover limits apply now?
L3. Is the VAT registration threshold now EGP 250,000 or still EGP 500,000?
L4. Is hosting abroad, or a foreign AI call with personal data, allowed without a permit? Which Egyptian cloud regions are usable?
L5. Typical B2B credit terms and cheque use for 10-100 staff firms; how common are post-dated cheques?
L6. Which accounting and ERP tools do accountants recommend and why; what would make them recommend a new one?
L7. Typical annual spend for software and accountant fees in our band, and what is acceptable to quote in EGP?
L8. Is Arabic required on invoices, and do owners expect Egyptian dialect in a chat?
L9. What is the real count of formal firms with 10-100 staff by sector (CAPMAS, ETA, MSMEDA)?
