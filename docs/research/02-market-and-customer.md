# 02 - Market and customer (KSA / UAE owner-led SMEs)

Access date for every URL below: 2026-11-04. Labels: **VERIFIED** (read at source or in a search excerpt of the source), **SECONDARY** (reported by press/vendor, primary not opened), **UNVERIFIED** (no source found), **ESTIMATE** (my arithmetic, assumptions shown).

Research limits, stated bluntly: official pages for Monsha'at (monshaat.gov.sa) refused connection and the BusinessWire release returned 403, so several figures come from press quoting them. No Reddit threads surfaced via search; "user sentiment" below is Capterra plus vendor/consultancy blogs (biased). No survey on how GCC SMEs buy ERP was found, so section 2 is mostly UNVERIFIED hypotheses to test in interviews.

---

## 1. Bottom-up size of the target segment

### 1.1 KSA firm counts

| Metric | Figure | Status | Source |
|---|---|---|---|
| Active commercial registrations (CRs), end Q3 2025 | ~1.7M | SECONDARY | https://www.arabnews.com/node/2621496/business-economy |
| Actual enterprises (one enterprise can hold several CRs) | ~1.3M | SECONDARY | https://www.qoyod.com/en/reports/saudi-smes-2026/ (vendor page citing Monsha'at) |
| Micro / small / medium, Q4 2023 SME Monitor | 1,138,588 / ~150,788 / ~18,723 | SECONDARY (latest split found; no 2024-25 split found) | search excerpt of Monsha'at report via https://www.onearabia.me/local/saudi-arabia-sme-growth-q4-report-highlights-011-7061.html |
| Size bands: micro 1-5 employees (<=SAR 3M rev), small 6-49 (SAR 3-40M), medium 50-249 (SAR 40-200M); higher category wins | per Monsha'at | VERIFIED via search summary of official FAQ | https://monshaat.gov.sa/en/node/12771 and https://www.monshaat.gov.sa/en/SMEs-definition |
| SME employment | >8.4M (Aug 2025) | SECONDARY | https://www.arabnews.com/node/2621496/business-economy |
| Regional concentration | Riyadh 39%, Makkah 17%, Eastern 16% | SECONDARY (vendor) | https://www.qoyod.com/en/reports/saudi-smes-2026/ |

Note: ~87% of KSA enterprises are micro (1,138,588 / 1,308,099 = 87.0%, ESTIMATE from the above). They are mostly not ERP buyers.

### 1.2 UAE firm counts

| Metric | Figure | Status | Source |
|---|---|---|---|
| All companies, end 2025 | >1.4M (250k added in 2025) | SECONDARY | https://www.thenationalnews.com/business/economy/2026/01/06/uae-adds-250000-more-companies-in-2025-as-llc-rules-simplified/ ; https://www.emirates247.com/business/economy-finance/more-than-1-4-million-companies-operating-in-uae-minister-of-economy-2026-01-07-1.743362 |
| SMEs, end 2022 (MoE) | 557,000; target 1M by 2030 | SECONDARY | https://arabianbusiness.com/politics/uae-has-557000-smes-targets-1m-by-2030 |
| SME share of firms | ~94% | SECONDARY | Khaleej Times via search: https://khaleejtimes.com/business/mergers-to-boost-uaes-small-business-sector |
| SME split micro/small/medium 72/18/10% | undated, "Dubai" label, deck | UNVERIFIED | https://www.mbgcorp.com/ae/saseraf/2024/10/Market-Research-Deck-for-European-clients.pdf |
| SME size classes (sector-specific thresholds) | exist | not extracted | https://added.gov.ae/Our-Initiatives/SME-Definition |

Problem: the UAE total counts licences, including free-zone and dormant/holding shells; no official size split by employees was found. Treat UAE numbers as upper bounds.

### 1.3 Target definition and arithmetic (all ESTIMATE)

Target = owner-led firms with roughly 10-200 employees (Monsha'at "small, upper half" + "medium").

**KSA**
- Small (6-49) 150,788 x 60% (ASSUMPTION: 60% of small firms have >=10 employees; no source) = 90,473
- Medium (50-249) 18,723 x 100% (slight overcount of the 201-249 slice; ignored) = 18,723
- KSA target firms ~ 109,196 -> **~109k**. Data is Q4 2023; growth since is not applied (conservative).

**UAE**
- 557,000 SMEs x 28% (small 18% + medium 10%, UNVERIFIED split) = 155,960
- Of which >=10 employees: small 100,260 x 60% + medium 55,700 = 115,856
- Haircut 50% for multi-licence, free-zone shells, non-operating entities (ASSUMPTION; no source) = ~57,900 -> **~58k**. The 10% medium share looks too high relative to KSA's 1.4% medium (18,723 / 1,308,099), which is why I haircut hard.

**Combined target firms: ~167k** (109k + 58k). Plausible range 100k-220k.

### 1.4 TAM / SAM / SOM (ESTIMATE)

Pricing assumption for our product: blended ACV **US$4,800/yr** (US$400/month, e.g. ~15 users plus managed AI-built customisation). Benchmark: Odoo Custom plan list price US$16.40/user/month billed yearly (https://www.odoo.com/pricing-plan, VERIFIED): 15 users x 16.40 x 12 = US$2,952/yr = SAR 11,070 at 3.75 SAR/USD (peg, not re-sourced). Odoo licence is only part of the bill because implementation is separate (section 3), so US$4,800 all-in subscription is a premium positioning that must be justified by replacing partner implementation cost. ACV is a hypothesis, not data.

| Layer | Definition | Arithmetic | Result |
|---|---|---|---|
| TAM | every target firm buys at our ACV | 167,000 x $4,800 | **$801.6M** |
| SAM | firms that will adopt/replace an ERP-grade system within ~3 years: 25% (ASSUMPTION; no regional adoption-rate source found) | 167,000 x 25% = 41,750 firms; x $4,800 | **$200.4M** |
| Niche SAM | 3 chosen verticals = 30% of SAM (ASSUMPTION) | 41,750 x 30% = 12,525 firms; x $4,800 | **$60.1M** |
| SOM (3 yrs) | 3% of niche SAM | 12,525 x 3% = 376 firms; x $4,800 | **$1.8M ARR** |

Reading: a venture-scale outcome needs niche SAM expansion, a higher ACV (e.g. through services/payments/AI usage), or GCC-wide reach. $1.8M ARR in 3 years is a business, not a rocket, unless ACV and share assumptions are beaten. Sensitivity: each +1 pt of niche-SAM share = ~125 firms = ~$0.6M ARR.

### 1.5 Compliance forcing functions (demand timing; strongest verified signal)

- KSA ZATCA Phase 2: Wave 25 announced 24 July 2026, threshold halved to taxable turnover >SAR 187,500, integration from 1 Feb 2027; targeted taxpayers get 6 months notice. Wave 24 (>SAR 375,000) was due 30 June 2026. SECONDARY (EY / VATupdate excerpts): https://globaltaxnews.ey.com/news/2026-1705-saudi-arabia-announces-25th-wave-of-phase-2-e-invoicing-integration ; https://www.vatupdate.com/2026/08/11/zatca-announces-wave-25-of-e-invoicing-threshold-halved-to-sar-187500-integration-deadline-1-february-2027/ ; primary https://zatca.gov.sa/en/MediaCenter/News/Pages/Wave25-E-invoicing.aspx (not opened). Implication: tiny firms are now pulled in, but those under SAR 3M revenue are micro; our 10-200 target is already in-scope for most waves.
- UAE e-invoicing (Peppol PINT AE, via Accredited Service Providers): voluntary from 1 July 2026; mandatory reported as 1 Jan 2027 large businesses, 1 July 2027 smaller; source dates conflict (ASP deadline reportedly moved to 30 Oct 2026). SECONDARY, UNVERIFIED on MoF site: https://gulfnews.com/business/markets/uae-sets-new-rules-deadlines-for-businesses-on-using-digital-invoices-1.500287249 ; https://www.edicomgroup.com/blog/united-arab-emirates-electronic-invoicing-project ; https://www.fiscal-requirements.com/news/5848-uae-moves-toward-mandatory-e-invoicing-with-2027-phased-rollout

### 1.6 Promising niches (hypotheses, not sourced market sizes)

No credible vertical firm counts were found in this pass; ranking is by fit with pain points in sections 3-4. Next step: GASTAT/Monsha'at ISIC-level counts.
1. Trading / wholesale distribution (inventory, multi-branch, credit sales, VAT/e-invoice, Arabic documents). High invoice volume = high compliance pain.
2. Contracting, MEP, fit-out (project costing, retention, subcontractor payments, Arabic/English documents).
3. Clinics, dental and healthcare practices (billing plus insurance), if regulatory interfaces are tractable.
4. Light manufacturing / food production (BOM, batch, costing).
5. Services firms with recurring contracts (facility management, maintenance, cleaning, manpower supply: payroll, WPS/GOSI, Saudisation reporting).
Retail/F&B is crowded by POS-first vendors (e.g. Foodics, Qoyod): UNVERIFIED claim, check.

---

## 2. How owner-led businesses buy software/ERP in the region

Evidence quality: low. Searches returned no survey on channels or decision makers (query: GCC SME ERP buying process; results were vendor blogs, e.g. https://avmdevs.com/journal/erp-for-gcc-smes-when-worth-it, https://www.ssd4me.com/blog/our-blog-1/odoo-vs-sap-33). Everything below is a hypothesis to validate with 20-30 founder/CFO interviews.

- Decision maker (UNVERIFIED): owner/GM decides, finance manager or external accountant shapes the shortlist, IT rarely exists. One consultancy asserts the biggest failure is no internal owner (https://avmdevs.com/journal/erp-for-gcc-smes-when-worth-it, opinion).
- Channels (UNVERIFIED, plausible): (a) the external accountant/auditor/VAT consultant; (b) local implementation partner (SAP B1, Odoo, Microsoft, NetSuite resellers all sell through partners, see pricing pages in section 3); (c) peer referral in family/trade networks (wasta); (d) Google/WhatsApp inbound to partners; (e) ZATCA/Wave notices triggering urgent "I need a compliant system" purchases.
- Sales cycle (UNVERIFIED): partner-led ERP implementation timelines are reported as 10-17 weeks for NetSuite in UAE SMBs (https://lstconsultancy.com/netsuite-implementation-in-uae/ via search summary, vendor source); sales cycle itself not found.
- Buying criteria (SECONDARY, vendor opinion): brand recognition over fit is the typical mistake; some GCC SMEs are better served by accounting + a trade-specific ops system than a full ERP (same avmdevs link).
- Implication: the incumbent channel is the local implementation partner; a product that removes the partner needs another trusted channel (accountants, VAT consultants, banks, Monsha'at/Dubai SME programmes) and must handle the owner's low tolerance for a long project.

---

## 3. Typical SME ERP licence and implementation spend

All figures are partner/vendor marketing unless stated; ranges vary 2-5x for the same tier (flagged by the search summaries). Use as planning ranges only.

| Vendor | Licence | Implementation | Source / status |
|---|---|---|---|
| Odoo Enterprise (list) | Standard US$8.95/user/mo (yearly), US$11.20 monthly; Custom US$16.40 yearly, US$20.90 monthly; Light user US$2.90 | not included; Odoo.sh hosting for custom code extra | https://www.odoo.com/pricing-plan , VERIFIED |
| Odoo KSA partners | ~SAR 90-140/user/mo (partner-quoted) | SAR 45,000-110,000 or SAR 50,000-150,000 multi-module SME; low end SAR 9,000-40,000 for narrow scope; ZATCA add-on US$6,000-15,000 (one source) | https://www.iwesabe.com/erp-pricing-saudi-arabia ; https://todoops.sa/en/blog/odoo-pricing-guide-saudi-arabia-2025/ ; https://www.shyphan.com/blog/odoo-erp-cost-saudi.html ; SECONDARY (partner marketing) |
| SAP Business One (UAE) | not itemised | AED 25,000-75,000+, from AED 60,000, or AED 50,000-150,000 in an SME comparison | https://aganllc.com/blog/sap-business-one-dubai-price-implementation.html ; https://lstconsultancy.com/netsuite-vs-sap-business-one/ ; SECONDARY |
| NetSuite (UAE) | not itemised | AED 30,000-80,000 (one source) vs AED 100,000-500,000 (another); 10-17 weeks | https://lstconsultancy.com/netsuite-implementation-in-uae/ ; https://softartsolutionsinc.com/netsuite/netsuite-implementation-cost-in-the-uae/ ; SECONDARY, sources conflict |
| Zoho Books | per-org tiers with user allowance; global list US$15-20 (Standard) to US$60-70 (Premium) per org/month, sources inconsistent; UAE reseller AED prices dated Jan 2025 | small | https://www.zoho.com/ar-ae/books/pricing/ (not extracted); https://costbench.com/software/accounting/zoho-books/ ; SECONDARY |
| Dynamics 365 Business Central, local ERPs (Qoyod, Daftra, etc.) | no usable figures found | - | UNVERIFIED |

Takeaway (ESTIMATE): a 15-user Odoo deployment in KSA = licence ~SAR 11k/yr (computed above at list) + implementation SAR 50-150k one-off, so year-1 spend is 5-14x licence alone; implementation is the real market price we compete against: (50,000+11,070)/11,070 = 5.5x to (150,000+11,070)/11,070 = 14.5x. Odoo's low licence price anchors customers on "software is cheap", so our value must be sold against the implementation and upgrade bill, not the licence.

---

## 4. Why Odoo users leave or get frustrated

Evidence is mostly Capterra plus vendor/consultancy blogs (competitors with an incentive); no Reddit or G2 text retrieved.

1. **Upgrade breakage and cost.** Capterra reviewers say upgrades are time-consuming, disruptive and break customisations; one says it became expensive to maintain due to required customisation. https://www.capterra.com/p/135618/Odoo/reviews/ (SECONDARY; overall ~4.2 over ~1,300 reviews per search summary). Odoo's own docs: a database with custom modules cannot be upgraded until those modules exist for the target version, and custom code is not covered. https://www.odoo.com/forum/help-1/custom-modules-when-upgrading-odoo-on-odoo-sh-216194 (VERIFIED via search excerpt); also sequential upgrades only (https://oec.sh/blog/odoo-migration-complete-guide, vendor).
2. **Customisation cost and stalled projects.** Over-customisation plus poor transparency cited as a common cause of stalled projects. https://muchconsulting.com/blog/odoo-2/odoo-partner-switch-155 (Odoo partner blog).
3. **Partner dependence / lock-in.** Same source claims switching partner after go-live is ~75% of its cases (single-firm, self-reported; treat as anecdote). Enterprise users remain responsible for third-party and custom code.
4. **Cost growth.** Per-user pricing rises with users/features; Odoo.sh called prohibitive for very small firms (Capterra, same link); an agency claims ~$880/month hosting for 20 clients: https://deploymonkey.com/blog/agencies-moving-from-odoo-sh (competitor-vendor, treat with caution).
5. **Support.** Mixed: slow on cheaper plans, free support praised by others (Capterra).
6. **Arabic / ZATCA.** Odoo's Phase 2 module l10n_sa_edi appears to be Enterprise-only per a partner guide; structured address fields and invoice hash chain integrity cause failures if mishandled. https://ecosire.com/de/blog/odoo-saudi-arabia-localization-guide-2026 (partner, SECONDARY). No retrieved evidence on Arabic RTL/PDF problems: UNVERIFIED either way. Fact-check on Odoo GitHub/forum issues for l10n_sa_edi.

Interpretation (mine): the pain is not "Odoo is bad", it is that a customised ERP becomes a maintenance liability that only the original partner can touch. An AI-native builder that regenerates customisations across versions attacks exactly this, but also inherits it if it generates bespoke code per customer without a stable core.

---

## 5. Dubai Chamber AI-agents competition ("Create AI Agents Championship")

Organiser: Dubai Chamber of Digital Economy (DCDE). Official terms page (https://www.dubaichamberdigital.com/en/create-ai-agents-register-your-interest) gives NO dates, prize amounts, categories or rubric. The details below come from press/aggregators; BusinessWire release (https://www.businesswire.com/news/home/20261008883373/en/...) returned 403, not read.

- Launch/registration: opened 7 Oct 2026; registration closes December 2026 (no exact day); prototype + pitch deck + demo video due January 2027 (no day); semi-finalists Feb-Mar 2027, 12 finalists; grand final first week of May 2027. SECONDARY: https://tbreak.com/create-ai-agents-championship-dubai/ ; https://menastartupdigest.com/dubai-launches-aed2-5m-create-ai-agents-championship/ (one aggregator reportedly says registration closes 31 Jan 2027, conflicting; confirm with DCDE, WhatsApp +971 800 242 6237 per the official page).
- Categories: Societal, Personal, **Business** (public/private workflows, services, customer experience), Youth (<21). Each winner AED 550,000 (~US$150k) grant; AI Agent of the Year AED 1M; total >AED 2.5M. SECONDARY (same sources).
- Eligibility: open to anyone worldwide, solo or teams up to six, idea/prototype/early MVP stage; existing companies may enter a new agent/capability, **fully commercialised products are not eligible**; English only; original work; free entry, self-funded development. SECONDARY. Official page VERIFIED: no trade licence needed to enter, but **winners must have a Dubai-based company with a valid trade licence to receive funds**; finalists attend in person and pass security clearance; IP stays with participant (DCDE gets a non-exclusive promo licence); prize is non-transferable/non-cash-equivalent; jury decisions final and unexplained.
- Judging criteria: "predetermined criteria", not published (official page). Finalists reportedly must show a fully working agent live to jury, investors and officials (tbreak, SECONDARY). Rubric UNVERIFIED.
- Fit: a "Best Business AI Agent" entry should be a new, narrow agent (e.g. an AI agent that builds/maintains a ZATCA-compliant module for a vertical), not the whole ERP builder (risk of being deemed a commercial product). Budget a Dubai trade licence before May 2027.

---

## Five implications for niche selection

1. **Pick a niche where the incumbent's cost is partner implementation plus upgrades, not licence.** Odoo licence is ~SAR 11k/yr for 15 users but year-1 all-in is 5-14x that (section 3). A vertical with repeatable workflows lets AI replace partner hours; a one-off bespoke shape does not.
2. **Lead with compliance timing.** ZATCA Wave 25 (from 1 Feb 2027, >SAR 187,500) and UAE Peppol (2027) create dated, non-discretionary demand; prefer niches with high invoice counts per firm (trading, distribution, contracting) over low-frequency ones.
3. **Target 15-100 employee firms and avoid the micro tail.** ~87% of KSA enterprises are micro; the 10-200 band is ~109k KSA plus ~58k UAE (ESTIMATE, wide error bars). Validate the 60% and 50% assumptions with GASTAT/MoE microdata before sizing a round.
4. **Choose a niche with a trusted referral channel you can reach**: accountants/VAT consultants and trade associations, because partners are the incumbent route and buying evidence is thin. Interview 20-30 buyers per candidate niche before committing; the single biggest evidence gap in this document is buyer behaviour.
5. **Design for upgrade-safety and Arabic/ZATCA correctness as the product wedge**, since those are the verifiable Odoo grievances. Pair that with a narrow, shippable agent for the Dubai Business AI Agent category (deadline: registration Dec 2026, prototype Jan 2027, Dubai licence needed to collect), using the contest as cheap validation, not as the plan.
