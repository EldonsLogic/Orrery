# Readiness gates

Status: accepted
Owner: eldon

Current gate: G0

Gates replace dates. Work for a later gate may start early, but nothing counts as passed until every exit criterion below is met and written down. Plan rows carry their gate in [PLAN.md](PLAN.md).

**Changing the current gate** needs both founders in writing (a PR comment from each, or a signed line in the log) and an ADR in [decisions/](decisions/INDEX.md) that lists the evidence for each criterion. Then edit the `Current gate:` line above in the same PR.

## G0 Foundation
- Private org repo with branch protection, CI green, pre-commit installed on both machines.
- Rules, roles and logs in place (AGENTS.md, agents/, docs/log, docs/PLAN.md).
- Change-engine security fixes CE-SEC-001 to CE-SEC-004 done; no known open security bug in code that touches a real site.
- Founders' agreement signed, including IP assignment of the prototype.
- ADRs accepted by both founders: tenancy (0006), identity (0007), Blueprint contract (0003).

## G1 Spine proven
- A hand-written Blueprint compiles to a fresh tenant, applies, diffs and rolls back, on a real bench.
- A ZATCA Phase 2 invoice passes the ZATCA sandbox.
- Arabic bilingual tax invoice PDF reviewed by an Arabic-speaking accountant.
- Tenant creation is one scripted command; the 50-tenant spike has a written result.
- Counsel has answered the GPL boundary and vendor-certification questions in writing.
- Arabic eval set v0 and the model bake-off are done; a model tier list exists.

## G2 Pilot-ready
- One real business goes from discovery to a simulated Blueprint to live, with the human review gate and the one chat.
- Role-based views work for at least owner, accountant and sales roles.
- Tenant branding works end to end with guardrails (ADR-0014).
- Customer contract with the anonymised-reuse clause is signed for Pilot A.
- Eval thresholds are enforced in CI as a release gate.

## G3 Paying-customer-ready
- Security baseline checklist met; independent penetration test done and findings fixed or accepted in writing.
- Backups tested with timed restore drills; export and delete work and are verified.
- Billing, terms, privacy policy and DPA live; support process and status page running.
- UAE e-invoicing and payroll (WPS, GOSI) either shipped or explicitly excluded from the sold scope.

## G4 Repeatable
- Autonomy and reuse targets in [strategy/08](strategy/08-product-vs-software-house.md) met across several clients.
- Services share of revenue and setup margin on or above the table for the client count reached.
- Second vertical template and second market assessed with evidence.

## G5 Scale
- Self-serve signup with plan gating switched on.
- Second market live; certifications chosen and in progress.
- Hosting capacity plan proven at volume; custom domains available.
