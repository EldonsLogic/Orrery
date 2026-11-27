# ADR-0076: Phase-1 module scope adds ten modules as Blueprint components (contracts and ADRs first)

Status: Proposed
Owner: eldon
Approved by: Eldon 2026-11-27 (proposer); partner pending (his answers of 2026-11-27 are adopted below as constraints; approval on this PR)

## Context
Today's phase-1 core is accounting, sales, purchasing, inventory and VAT and e-invoicing ([module map](../product/module-map.md)). Eldon's view is that owner-led firms in the four markets also run customers, projects, staff, pay, zakat, shops and marketing in spreadsheets and WhatsApp, and expect one system to cover them (UNVERIFIED: a founder hypothesis, not yet tested in interviews). Eldon proposed adding ten modules to phase 1. The founders' amendment write-up is at https://claude.ai/artifact/SPYM4rBdFqUeDa1xHf76tp (outside the repo, read 2026-11-27). The GPL boundary for add-on engine apps is open: ADR-0074 (Proposed, PR #388, plan row LEG-006).

The partner's six answers (source: partner's message to Eldon, 2026-11-27, relayed in session), quoted verbatim:
1. Component per module: "yes, but contracts and ADRs only for now".
2. Add-on pins: "pin nothing until counsel has answered on the GPL boundary".
3. Core CRM instead of the AGPL CRM app: "yes".
4. POS: "don't adopt the Saudi POS app until its ZATCA claim has been reviewed; defer POS altogether".
5. Review changes: "accept Tier 1 for screen-only PRs and the automated first pass; hold \"fewer, bigger slices\" because it collides with the ~400-line PR rule".
6. Blocking or reordering G1: "yes, unless the builds wait for G2 or later; if they do go ahead, the rigid-zone modules (payroll, zakat, POS) come last".

## Decision
1. **Scope.** Phase 1 adds ten modules on top of the core: CRM; projects and boards (board, timeline and calendar views over the engine's Task and Timesheet); HR basics; payroll; an omnichannel inbox (WhatsApp, Instagram and Facebook through Meta's business platform); zakat; point of sale; e-commerce; manufacturing; marketing. The target segment does not change: these are modules for the trading and distribution niche. POS-first retail, F&B, manufacturers and e-commerce platforms stay rejected as customer segments ([niche](../strategy/02-niche-and-launch-country.md)); changing that needs its own strategy decision, not this ADR.
2. **Shape.** Each module is a Blueprint component ([component library](../architecture/component-library.md)) behind our own UI. The engine stays invisible ([ADR-0016](ADR-0016-engine-invisibility.md)). No per-client code ([ADR-0008](ADR-0008-no-client-specific-code.md)). Statutory parts come from country packs.
3. **Contracts and ADRs only for now.** This ADR changes scope, docs and plan rows. Nothing is built, pinned or installed under it.
4. **One GPL release condition: ADR-0074 Accepted.** No add-on engine app is pinned, installed or used until then. That holds ERP-042 (e-commerce on Webshop), ERP-043 (HR basics), ERP-038 (the HRMS skeleton bench run, which may not run before then), CMP-015 (payroll WPS file, and so CMP-016) and CMP-048 (payroll). HRMS is already in the pinned dev image; it stays unused for these until ADR-0074 is Accepted. LEG-006 being done is not the condition. ADR-0080 (Proposed, PR #400) also moves payroll and zakat logic outside the engine, into our own services.
5. **CRM uses the engine's core CRM doctypes** (lead, opportunity, customer, contact). The AGPL apps (CRM, Helpdesk, Insights, Gameplan and others) are never used. Their AGPL-3.0 licences are recorded with sources in the licence register's forbidden list (ADR-0080, PR #400; GitHub licence API, accessed 2026-11-27).
6. **Point of sale is deferred entirely.** No POS contract or build starts before CMP-050 reviews the Saudi POS app's ZATCA claim. The write-up does not name the app or its repository (UNVERIFIED); CMP-050 first identifies it and checks its licence.
7. **Review tiers. This narrows ADR-0035 item 1.** A screen-only PR may be Tier 1 (merges on green CI, the other founder skims afterwards) only when all hold: it changes only screen files under `web/` on fixtures; it touches no auth, tenancy, contracts, money, connectors or rigid-zone code; strings go through i18n and styles through tokens; and the automated first-pass review (QA-025) has run on it with no blocking finding. Until QA-025 is done, screen PRs stay Tier 2. Everything else keeps its ADR-0035 tier. PRs stay at about 400 changed lines or less; "fewer, bigger slices" is not adopted.
8. **Gates and order.** Every build row is `blocked` until G2, or both founders' written agreement. The rigid-zone modules (payroll, zakat, POS) come last in every case, after the non-rigid modules ship.
9. **Rigid zone, under ADR-0031 unchanged.** Payroll, zakat and POS receipts (CMP-048, CMP-049, CMP-051) are rigid zone. Coding agents may write their code only under ADR-0031's four conditions: official test vectors with source and access date, a line-by-line review by a founder who did not prompt it, a qualified accountant's review of the maths before any real data, and a logged model and prompt. Each is Tier 3 and needs the accountant's sign-off before real use. The engine, or a vetted component, stays the one calculation authority. Separately, the product's own AI never drafts or generates components that touch ledger, tax, stock or permissions at runtime (BPL-016; the Q-421 proposal on PR #372 is not agreed, so that stricter rule stands). Eldon's decision, 2026-11-27: this ADR does not narrow ADR-0031, because 'human-written only' was rejected in ADR-0031 as unworkable and Q-421 concerned runtime drafting, not coding agents. For zakat, Seshna prepares the figures and the worksheet; the company files its own return.
10. **Other rigid boundaries.** Manufacturing: stock entries, valuation and work-order costing postings to the ledger are rigid zone, computed by the engine as the one calculation authority (ADR-0031); any code that computes or posts them is Tier 3, screens and configuration are Tier 2. Web shop: invoices, VAT and e-invoicing are rigid zone and Tier 3; the shop creates orders, and invoices and VAT come from the engine and the e-invoicing path, never from shop code. Payments are Tier 3 (money).
11. **Payments.** A bring-your-own-gateway connector: hosted checkout or tokens only, no card data touches Seshna, and Seshna holds no merchant account (DSC-021).
12. **Customer go-live items.** Each customer's payment gateway account, Meta business verification and templates, and SMS sender approvals are that customer's go-live items, not build items.

## Alternatives rejected
- Keep phase 1 to the core five and add modules later: owners would still need a second tool for customers, staff and projects.
- Use the AGPL apps: the AGPL network clause (section 13) conflicts with an invisible, never-distributed engine (research note `docs/research/gpl-saas-boundary.md` row 5, PR #388, accessed 2026-11-27).
- Pin HRMS functions and Webshop now: the GPL boundary is unanswered (ADR-0074).
- Build POS now on the Saudi POS app: its ZATCA claim is unreviewed (UNVERIFIED), and POS receipts are rigid zone.
- A Seshna merchant account: it would make us a payment intermediary holding card data, with licensing duties in four markets (UNVERIFIED: not yet researched).
- Larger PRs to move faster: review quality drops; the 400-line limit stays.

## Consequences
- Easier: one scope everyone plans against; contract work can start now without waiting for the GPL answer.
- Harder: ten more modules to keep Arabic-first, tokenised and invisible-engine; more connectors with untrusted inbound content (Meta, SMS); Meta would likely be a new processor under PDPL (INFERENCE, to confirm with counsel).
- Plan rows: contracts at G1 (DSC-021, DSC-022, BPL-052 to BPL-055, delivered by PRs #393 to #398); builds at G2, `blocked` per item 8 (DSC-023, DSC-024, BPL-056 to BPL-059, WEB-031 to WEB-035); QA-025 at G2; email marketing (Eldon, 2026-11-27): the DSC-025 email connector contract and BPL-066 email additions at G1, the DSC-026 connector build and WEB-037 email builder screens at G2; held rows sit at G3, so every module except point of sale lands in phase 1 by G3 (Eldon, 2026-11-27): ERP-042, ERP-043, CMP-048, CMP-049 and the POS review CMP-050. Point of sale itself (CMP-051) is the only module still waiting, parked at G4 after CMP-050 (ADR-0025). The rows blocked on ADR-0074 hold G3 until it is Accepted, which is intended. Payroll and zakat stay last within G3 (item 9). ERP-038 and CMP-015 stay at G2 and G3 but are `blocked` under item 4, so they hold those gates until ADR-0074 is Accepted. CMP-013 and CMP-015 stay slices of CMP-049 and CMP-048 with their owner and gate.
- Amends, on acceptance: [phased-delivery-and-lanes.md](../architecture/phased-delivery-and-lanes.md) "payroll calculation (file export only)" and the version-one exclusion of point of sale (edited in this PR); RULES 34 "HRMS only as a skeleton" (HR basics and payroll may use HRMS functions once ADR-0074 is Accepted; the rule text changes after acceptance); NOTICE.md's HRMS row (edited here) and new Webshop and POS rows; [core-module-scope-trading.md](../specs/core-module-scope-trading.md), whose v1 exclusions of Manufacturing, Projects, CRM and POS this ADR lifts for phase 1.
- This ADR does not touch the human floor ([ADR-0027](ADR-0027-human-floor-action-policy-and-agent-authority.md)), lanes, gates or the phase exit check.

## Supersedes
None. Narrows ADR-0035 item 1 (item 7); ADR-0031 applies unchanged (item 9); amends the documents listed above.
