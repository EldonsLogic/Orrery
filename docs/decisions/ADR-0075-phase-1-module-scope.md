# ADR-0075: Phase-1 module scope adds ten modules as Blueprint components (contracts and ADRs first)

Status: Proposed
Owner: eldon
Approved by: Eldon 2026-11-27 (proposer); partner pending (his answers of 2026-11-27 are adopted below as constraints; approval on this PR)

## Context
Today's phase-1 core is accounting, sales, purchasing, inventory and VAT and e-invoicing ([module map](../product/module-map.md)). Owner-led firms in the four markets also run customers, projects, staff, pay, zakat, shops and marketing in spreadsheets and WhatsApp, and expect one system to cover them. Eldon proposed adding ten modules to phase 1; the partner (sayegh9) answered on 2026-11-27 with six conditions. The founders' amendment write-up is at https://claude.ai/artifact/SPYM4rBdFqUeDa1xHf76tp (outside the repo). The GPL boundary for add-on engine apps is open: ADR-0074 (Proposed, PR #388, plan row LEG-006).

## Decision
1. **Scope.** Phase 1 adds ten modules on top of the core: CRM; projects and boards (a board, timeline and calendar view, in the style of monday.com, over the engine's Task and Timesheet); HR basics; payroll; an omnichannel inbox (WhatsApp, Instagram and Facebook through Meta's business platform); zakat; point of sale; e-commerce; manufacturing; marketing.
2. **Shape.** Each module is a Blueprint component ([component library](../architecture/component-library.md)) behind our own UI. The engine stays invisible ([ADR-0016](ADR-0016-engine-invisibility.md)). No per-client code ([ADR-0008](ADR-0008-no-client-specific-code.md)). Statutory parts come from country packs ([country packs](../architecture/country-packs.md)).
3. **Contracts and ADRs only for now.** This ADR changes scope, docs and plan rows. Nothing is built, pinned or installed under it.
4. **No add-on engine app is pinned or installed until ADR-0074 is answered.** That holds back the builds of HR basics and payroll (HRMS functions) and e-commerce (the engine's Webshop app). HRMS is already in the pinned dev image ([engine version policy](../architecture/engine-version-policy.md)); it is not used for these modules until ADR-0074 is accepted.
5. **CRM uses the engine's core CRM doctypes** (lead, opportunity, customer, contact). The separate AGPL apps (the CRM app, Helpdesk, Insights, Gameplan and others) are never used.
6. **Point of sale is deferred entirely** until the Saudi POS app's ZATCA claim has been reviewed (CMP-050). No POS contract or build starts before that.
7. **Review tiers.** Tier 1 for screen-only PRs that touch no auth, tenancy, contracts or money, plus an automated first-pass review. Everything else keeps its tier. PRs stay at about 400 changed lines or less; no "bigger slices".
8. **Gates.** Builds wait for G2 or later unless both founders agree in writing. If they start earlier, the rigid-zone modules (payroll, zakat, POS) come last.
9. **Rigid zone.** Payroll, zakat and POS receipts are rigid zone: deterministic code, Tier 3 review, and a qualified accountant's sign-off before any real use. AI never writes that logic (AGENTS.md principle 3; the Q-421 proposal on PR #372 is not agreed). For zakat, Seshna prepares the figures and the worksheet; the company files its own return.
10. **Payments.** A bring-your-own-gateway connector: hosted checkout or tokens only, no card data touches Seshna, and Seshna holds no merchant account (DSC-021).
11. **Customer go-live items.** Each customer's payment gateway account, Meta business verification and templates, and SMS sender approvals are that customer's go-live items, not build items.

## Alternatives rejected
- Keep phase 1 to the core five and add modules later: owners would still need a second tool for customers, staff and projects, which weakens the one-system pitch.
- Use the AGPL apps (CRM, Helpdesk, Insights, Gameplan): the AGPL network clause conflicts with an invisible, never-distributed engine; the core doctypes cover what phase 1 needs.
- Pin HRMS functions and Webshop now: the GPL boundary is unanswered (ADR-0074); building on them first could force a rewrite.
- Build POS now on the Saudi POS app: its ZATCA claim is unreviewed, and POS receipts are rigid zone.
- A Seshna merchant account for payments: it would make us a payment intermediary with card data and licensing duties in four markets.
- Larger PRs to move faster: review quality drops; the 400-line limit stays.

## Consequences
- Easier: one scope everyone plans against; contract work (Blueprint, connector) can start now without waiting for the GPL answer.
- Harder: ten more modules to keep Arabic-first, tokenised and invisible-engine; more connectors with untrusted inbound content (Meta, SMS) and a new processor (Meta) under PDPL.
- Must do (plan rows): payments connector contract DSC-021 and build DSC-023; messaging and SMS connector contract DSC-022 and build DSC-024; Blueprint contract additions BPL-051 (CRM), BPL-052 (projects and boards), BPL-053 (manufacturing), BPL-054 (marketing); component builds BPL-055 to BPL-058 (partner, G2); screens WEB-031 to WEB-035 (G2); held rows ERP-042 (e-commerce), ERP-043 (HR basics) and CMP-048 (payroll) blocked on ADR-0074; CMP-049 (zakat) held as rigid zone, last; CMP-050 (POS ZATCA claim review) and CMP-051 (POS, deferred). Existing rows CMP-013 (zakat report) and CMP-015 (payroll WPS file) are slices of CMP-049 and CMP-048 and keep their owner.
- The module map and its v1 not-doing list change (manufacturing depth and e-commerce leave it; POS-first retail stays deferred; filing tax or zakat for customers stays not-doing).
- This ADR does not touch the human floor ([ADR-0027](ADR-0027-human-floor-action-policy-and-agent-authority.md)), lanes, gates or the phase exit check.

## Supersedes
none
