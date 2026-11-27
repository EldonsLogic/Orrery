# ADR-0080: Rigid-zone and country business logic lives in our own services, outside the engine process

Status: Proposed
Owner: eldon
Approved by: Eldon (proposer, 2026-11-27); partner pending on this PR. The four points come from the partner (sayegh9), 2026-11-27.

## Context
The partner raised four GPL points on 2026-11-27:
1. A payroll component built inside an engine app that imports HRMS would very likely be a GPL derivative. It could then never ship on-premises or to a reseller under proprietary terms. GOSI, Mudad, end-of-service and zakat logic is our most valuable IP and belongs in our own services that call the engine over its API.
2. No engine JS, CSS or templates ever reach a customer's browser; generated PDFs are output, not code.
3. Later handovers count as distribution: on-premises (LEG-017, G5), full bench backups that include code, sharing components with partners, and possibly acquisition due diligence.
4. The licence register lists only the lavaloon app as forbidden; the AGPL apps must be added.

The research note `docs/research/gpl-saas-boundary.md` (branch `leg-006-gpl-saas-research`, ADR-0074, both Proposed) supports this. Hosted use with no copy handed over is not conveying (GPL-3.0 s.0, s.2). Under the FSF's view, though, in-process Python apps that import ERPNext or HRMS are probably works "based on" them (WIDELY HELD, not tested in court). That costs nothing while we never convey. The day we convey, those apps must go out under the GPL (s.5(c)). Today our engine app imports ERPNext and HRMS only in tests and proofs (`git grep`, 2026-11-27).

ADR-0076 (Proposed, branch `gov-078-module-scope`) adds payroll (CMP-048) and zakat (CMP-049) as Blueprint components, but it does not say where their logic runs.

## Decision
1. **Business logic outside the engine.** Our own deterministic services hold the rigid-zone and country-specific business logic, outside the engine process, and they call the engine over its API through the engine adapter ([engine-adapter.md](../architecture/engine-adapter.md)). This covers:
   - payroll and its statutory files (GOSI, Mudad, WPS);
   - end-of-service;
   - zakat;
   - e-invoicing rules;
   - tax rules;
   - the valuation policies we own.

   Each service stores its own rules and results. It reads and writes engine records only through the adapter's `query` and `execute`. The rigid-zone rules still apply (RULES 21): the logic is deterministic code, never AI-written, with Tier 3 review.
2. **Thin engine apps.** Engine apps under `apps/engine/` are thin adapters: hooks, fixtures, doctype wiring, guards and the change engine's apply path. They hold no business logic of the kind listed in point 1. They do not import `erpnext` or `hrms`, except in tests and proofs.
3. **Our services never import `frappe`, `erpnext` or `hrms`.** This covers everything under `services/` and any other code of ours that runs outside the engine process.
4. **Amends ADR-0076 for payroll and zakat.** CMP-048 (payroll) and CMP-049 (zakat) are built as our own services under point 1. Their engine side is limited to the records and fixtures they need. The existing slices follow this ADR: CMP-013 (zakat report) and CMP-015 (payroll WPS file), and with them CMP-016 (GOSI). This does not change ADR-0076 point 4: no HRMS function is used for these modules until ADR-0074 is answered. It also leaves the owners of those rows unchanged.
5. **Enforcement.** CI checks enforce points 2 and 3, together with the browser asset rule in engine-adapter.md "Licence boundary". The checks are QA-022, QA-023 and QA-024.

## Why
- **GPL derivation.** Logic that imports ERPNext or HRMS in the same process is probably a derivative work (FSF #MereAggregation, #IfInterpreterIsGPL; research note 3a). Keeping it in separate services that talk over an API keeps it at arm's length (#GPLInProprietarySystem).
- **Options stay open.** On-premises (LEG-017), resellers, partner sharing and a sale of the company all hand over copies. Logic kept outside the engine stays ours to license on any terms. Logic kept inside it would have to go out under the GPL.
- **IP.** The statutory engines (GOSI, Mudad, end-of-service, zakat, e-invoicing rules) are what is hard to copy. They are our moat, and the engine is replaceable (engine-adapter.md "Replaceability test").

## Alternatives rejected
- **Build payroll as an engine app on HRMS.** It is fastest to start, but it very likely makes the logic GPL the first time we convey. It also ties our IP to one engine.
- **License our engine apps GPL and keep all logic there.** It is legal while we stay SaaS only, but it gives away the most valuable code. It also closes the on-premises and reseller options without counsel.
- **Decide later, case by case.** Moving logic out after it has grown inside the engine is a rewrite. The partner's point is to decide before CMP-048 and CMP-049 start.

## Consequences
- **Cost: API round trips.** A payroll run reads employees and attendance and writes salary journals through the adapter, not through in-process calls. That is slower and needs batching and paging in the adapter (`query`, `execute`).
- **Cost: transactions.** Transactional consistency across our service and the engine is no longer a single database transaction. The engine adapter handles it: idempotent `execute` with request ids, the change engine's journal and rollback for configuration, and compensating postings for business records. Each rigid-zone service states its consistency design in its spec before it is built.
- Engine-side reports that would have run on HRMS data are rebuilt on our services' own stores, or read through the adapter.
- HRMS stays a data skeleton at most (ERP-010, ERP-038). Its functions are not used for statutory logic.
- New plan rows: GOV-079 (this ADR and its doc edits), QA-022 (eldon: the services import check), QA-023 (partner: no engine asset routes in the gateway), QA-024 (partner: the apps/engine import check).
- The licence register now lists the AGPL apps as forbidden and adds the rule to re-check licences at every engine bump.

## Supersedes
None. Amends ADR-0076 for payroll and zakat (point 4).
