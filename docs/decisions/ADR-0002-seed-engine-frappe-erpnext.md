# ADR-0002: Seed engine is Frappe + ERPNext, behind an adapter

Status: Accepted
Owner: eldon
Approved by: Eldon and partner

## Context
Writing a ledger from scratch is the biggest correctness risk for two founders using AI coding tools ([../strategy/04-architecture-and-seed.md](../strategy/04-architecture-and-seed.md), [../strategy/01-gaps-and-risks.md](../strategy/01-gaps-and-risks.md) risk 7). Frappe Framework is MIT; ERPNext and HRMS are GPL-3; ERPNext is about 89% translated to Arabic (measured, strategy/04).

## Decision
Use Frappe + ERPNext as the rigid engine, one site per tenant, run as SaaS only and never distribute it to customers without legal review. Our AI services, compiler, UI and control plane are separate services that talk to the engine over API and are not linked into the GPL process. The engine sits behind an adapter so it can be replaced. ZATCA comes from the MIT-licensed ERPGulf app, not the AGPL lavaloon app. HRMS is used only as a skeleton. One consistent Frappe/ERPNext/HRMS version set is pinned (likely v15, to confirm). This decision is gated by the G1 spike (ERP-001 to ERP-003, CMP-002 to CMP-004); if the spike fails we revisit.

## Alternatives rejected
- Own thin engine: slower, accounting risk.
- Odoo CE, Open Mercato, Twenty, NocoBase: licence or fit problems (strategy/04, strategy/09).

## Consequences
- Fast path to a working ledger, stock and tax.
- GPL boundary must be reviewed by counsel (LEG-006); hybrid or on-prem is blocked until then (LEG-017).
- Never use the words ERPNext or Frappe in the product name or ads.
- Engine upgrades follow a written policy (ERP-004).

## Supersedes
none
