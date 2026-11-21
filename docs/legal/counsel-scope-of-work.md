# Counsel scope of work (LEG-003)

Status: draft for the founders to send
Owner: eldon

This is the brief the founders send to prospective counsel in Saudi Arabia, the UAE, Egypt and Qatar. It is not legal advice and states no legal conclusion. Every factual or legal claim below is UNVERIFIED until counsel confirms it. Tags show the plan row ([../PLAN.md](../PLAN.md)), open question ([../open-questions.md](../open-questions.md)) and gate each answer unblocks. Sources: [checklist.md](checklist.md), [../research/03-regulations.md](../research/03-regulations.md), [ADR-0016](../decisions/ADR-0016-engine-invisibility.md), [ADR-0024](../decisions/ADR-0024-four-phase-1-markets.md).

## 1. Purpose and the company in brief
Two founders are building an AI-native business platform for owner-led companies (10 to 100 staff) in Saudi Arabia (KSA), the UAE, Egypt and Qatar. A chat interviews the owner in Arabic or English, drafts a configuration, assembles an ERP from vetted open-source components, and runs it as software as a service (SaaS). Ledger, tax, e-invoice and payroll maths are deterministic code; AI drafts and humans approve. Working name is not cleared. No entity exists yet. No customer data is held. Phase 1 runs in all four markets with no fixed launch order.

We want, per market, written answers to the questions below, so we can pick an entity, a hosting and AI-provider set-up, a name, and a contract set before we take real customer data.

## 2. Priorities
Gate G0/G1 first (sections 3.1 to 3.4, 3.6, 3.7 name clearance), then G2 (entity, data, contracts), then G3 and later. Ask for a fixed-fee quote per section, and say which questions you would answer from the market you practise in and which need a correspondent firm.

## 3. Questions
Tags: `[row | Q | gate]`. M = every market; KSA, UAE, EG, QA = market-specific.

### 3.1 Entity, licensing and tax position of our own sales
1. Which entity or entities should contract with, invoice and collect from customers in each market, and what registration (commercial registration, licence, local agent or reseller) is needed to do so in SAR, AED, EGP and QAR? [LEG-010 | checklist 2, 12, E-1 | G2] M
2. UAE: compare a mainland trade licence in Dubai with a free-zone or other licence for a software and SaaS business. State activity wording, local-service-agent or ownership limits, bank-account practice and ongoing cost, without recommending on price alone. [LEG-010 | - | G2] UAE
3. UAE entity serving KSA customers: may it contract and invoice Saudi customers cross-border without a Saudi entity or commercial registration? Does it need Saudi VAT registration or create a permanent establishment? What follows if KSA tenants are hosted in-Kingdom? [LEG-011 | checklist 2 | G2] KSA, UAE
4. Same question for Egypt and Qatar customers served from a UAE (or other) entity. [LEG-010 | Q-201, E-1 | G2] EG, QA
5. Tax position of our own subscription and setup invoices: VAT, withholding, reverse charge, invoice format and currency in each market. [LEG-010, LEG-013 | Q-402, checklist 17, E-2 | G2] M
6. Do any of our features (payroll file generation, tax data preparation, e-invoice submission) make us a regulated service such as a tax agent or a salary-payment channel? [CMP-001 | research q11 | G1] KSA, UAE, EG, QA
7. Founders' agreement and cap-table terms: scope only, quote separately. [FND-007 | checklist 1 | G3] M

### 3.2 Open-source licence boundary and notices
8. Our engine is GPL-3 software (ERPNext, HRMS) run headless on our servers behind our own gateway and web app, reached only by API, never given to customers. Does that architecture avoid distribution and derivative-work issues in your market's law? State the facts and assumptions your opinion rests on. [LEG-006 | checklist 4 | G1] M
9. Is any customer-visible open-source notice required for the engine in a SaaS? ADR-0016 allows one notices page only if you confirm it is required. [LEG-018 | - | G1] M
10. Trademark policy of the engine's owners: what may we say about compatibility, and what must we avoid in product name, ads and documentation? [LEG-009 | checklist 16 | G1] M
11. Later, if we ship a hybrid or on-premises build: what changes? Scope as an optional second phase. [LEG-017 | - | G5] M
12. Review one redis-image licence reading we have already made. [LEG-004 | Q-15 | G1] M

### 3.3 E-invoicing vendor duties
13. ZATCA: beyond the developer SDK, sandbox and simulation, is any vendor certification, registration, listing or contract needed to sell software that generates Phase 2 e-invoices? [LEG-007 | research q1, K4 | G1] KSA
14. UAE: does software that generates PINT AE invoices for taxpayers need any status of its own (software vendor, accredited service provider or other), or only each tenant's appointed provider? Split liability between us, the provider and the tenant. Final schedule and B2C exclusion. [CMP-009, LEG-007 | Q-210, research q2, q3 | G2] UAE
15. Egypt: e-invoice and e-receipt duties for small firms and any registration for software vendors; the VAT threshold figures conflict across our sources. [CMP-001, GTM-017 | Q-215, E-4 | G2] EG
16. Qatar: any current or announced e-invoicing duty and vendor obligation. [CMP-001 | CMP-030 | G1] QA
17. Arabic, Hijri-date and retention rules for invoices and books, and who bears the archiving duty (including a Qatar "books kept in country" rule against cloud hosting abroad). [CMP-001, LEG-019 | Q-206, research q4, q5 | G1] M

### 3.4 Data protection, hosting and AI providers
18. KSA PDPL: which transfer mechanism is acceptable for hosting outside the Kingdom and for sending prompts or documents to a large-language-model provider abroad? Is in-Kingdom hosting mandatory for ERP data? Must we register as a processor with the regulator, and appoint a DPO? [LEG-012, CMP-019 | Q-10, research q6, q10 | G2] KSA
19. KSA AI and data-hosting rules, NCA cloud controls and CST cloud registration: which apply to us as a SaaS vendor serving private companies, and to which customers? [CMP-019, CMP-018 | research q7 | G0] KSA
20. UAE: PDPL status and executive regulations, free-zone regimes (DIFC, ADGM) if we or customers sit there, and transfers to foreign LLM providers. [LEG-012 | research q8, q10 | G2] UAE
21. Egypt: does hosting abroad or calling a foreign AI model need a data-protection centre permit? Do we need a processor licence and a DPO? When is Law 151 of 2020 enforced in practice? [LEG-012 | Q-199, E-3 | G1] EG
22. Qatar: data localisation, the 72-hour breach clock, and processor duties for a SaaS holding HR data. [LEG-012 | Q-204 | G1] QA
23. Cross-market identity store: may one central store hold names, contacts, login logs and MFA factors across four countries, and may our staff abroad access in-country tenant data? [INF-001, PLT-005 | Q-14, Q-9 | G1] M
24. Model-provider terms (no training, retention, region): which clauses must we require, and what customer consent language is needed for foreign-region endpoints? [LEG-012, PLT-010 | Q-10, checklist 18 | G2] M
25. Breach notification and records-of-processing duties we can build into the incident plan and PDPL programme. [SEC-013, CMP-017 | - | G3] M

### 3.5 Customer contract, IP and anonymised reuse
26. Customer master agreement for fixed setup fee plus subscription, no free pilots: governing law, language (Arabic or bilingual), dispute venue, currency and collection rules per market. [LEG-013, GTM-005 | checklist 7, 8, E-5, E-6 | G2] M
27. Anonymised-reuse clause: wording and enforceability for licensing de-identified configuration patterns and components for reuse across customers; no training on tenant data. [LEG-013, DAT-008 | checklist 14 | G2] M
28. Who owns the configuration we draft for a customer, and the components we build once for everyone? [LEG-013 | - | G2] M
29. Liability cap and disclaimers for AI-drafted configuration that a human approves; human-review gate language. [LEG-013 | research q15 | G2] M
30. Terms of service, privacy notice, data processing agreement and sub-processor process, in Arabic and English; cookie and consent wording. [LEG-015, WEB-002 | checklist 9 to 14 | G3] M
31. Tenant-uploaded logos and content: warranties, licence and takedown. [LEG-015 | checklist 13 | G3] M

### 3.6 Name clearance and trademarks
32. Search and written opinion on our working name and short-listed alternatives, in Latin and Arabic spelling, in KSA, UAE, Egypt, Qatar and internationally, for software and SaaS classes; domains and handles. Filing strategy and cost per market. [LEG-008, LEG-005 | checklist 6, E-7 | G1] M
33. Is a cleared name needed before we register the entity or sign a first customer? [LEG-008, BRD-003 | - | G1] M

### 3.7 Employment, contractors and IP
34. IP assignment from founders and contractors to the company, including code and history from an earlier prototype. [LEG-014 | checklist 3 | G2] M
35. Contractor and employee templates with confidentiality and an AI-tool use policy; labour-law traps in each market for hiring remote staff. [LEG-014 | checklist 15 | G2] M

### 3.8 Insurance
36. Professional indemnity and cyber cover: what is required, available and sensible per market, given compliance output risk. Broker introductions welcome. [LEG-016 | checklist 16 | G3] M

## 4. Deliverables
- A written opinion per market (or per topic where the answer is common), with facts relied on, assumptions, confidence, sources (statute, article, regulator page) and the date each was read.
- A clear list of what you could not confirm, and what needs a regulator's written answer; offer to ask the regulator.
- Redlines or first drafts for 3.5, 3.7 and ToS, privacy and DPA documents; Arabic and English where the law requires.
- A one-page summary per section ending in recommended next actions and open risks.
- Fixed-fee or capped estimate per section, hours by seniority, and the correspondent firm for any market you do not cover.

## 5. What we provide
Anonymised architecture and licence summaries, the questions above, draft contract skeletons, and the product description. No customer data, no real pilot data, no credentials. We will share only what you request and only under your engagement letter.

## 6. Firm selection checklist (founders)
- Software, SaaS and technology-regulation experience in the market; has advised on data-protection and e-invoicing for vendors, not only for taxpayers.
- Open-source licensing competence (GPL) in-house or through a named international firm.
- Native Arabic drafting for contracts and notices; English working language with us.
- Conflict check against ERP vendors and the engine's owners.
- Responsiveness: named partner, turnaround per section, fixed or capped fees.
- Correspondent network covering the other three markets, or a lead firm that coordinates all four.
- Willing to opine in writing, not only by call; willing to approach regulators.
- Professional indemnity insurance and written confidentiality terms.
- Any firm named by the founders needs its details checked on an official firm or bar page (cite URL and access date, YYYY-MM-DD) before the engagement letter.

## 7. Confidentiality
Share this document only after a signed non-disclosure agreement or engagement letter. It contains our product approach and open doubts, but no customer data.

## 8. Notes for the founders (remove before sending)
- The Dubai AI championship and accelerator-evaluation documents named for entity input were not found in `docs/`; add their entity questions here if they exist elsewhere.
- Decide: one lead firm coordinating four markets or four firms; whether to include the optional items (7, 11, 12).
