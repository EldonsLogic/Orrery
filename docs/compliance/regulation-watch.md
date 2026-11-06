# Regulation watch

Status: draft
Owner: unassigned

Rules move often (UAE e-invoicing dates changed twice in 2026; ZATCA thresholds step down each wave, [../research/03-regulations.md](../research/03-regulations.md)). This process keeps all tenants current.

## Who
| Role | Duty |
|---|---|
| Watch owner (one founder, named in PLAN) | Weekly check of sources, logs changes |
| Compliance reviewer (counsel or tax adviser, external) | Confirms interpretation of material changes |
| Engineer on duty | Implements config or component change, runs tests |

## Sources (check weekly, record access date)
ZATCA news and e-invoicing pages; ZATCA developer portal and SDK releases; ERPGulf app releases; MoF and FTA (UAE) e-invoicing pages; accredited provider notices; SDAIA; UAE data regulator; MOHRE, HRSD, GOSI, Mudad; NCA; law-firm alerts (secondary, verify). Add sources as found.

## Process
1. Detect: change found by watch owner or alert (RSS/email).
2. Log in the regulation register (table in [country-matrix.md](country-matrix.md) updated with URL and date; label SECONDARY until read in the official source).
3. Triage: impact (none, config, component code, contract/legal, customer notice) and urgency by effective date.
4. Decide: material changes need an ADR (trigger: new mandate, changed deadline affecting customers, new data-transfer rule, changes to rigid-zone logic).
5. Implement: change effective-dated config or certified component version (deterministic code, tests, sandbox); never ad hoc per tenant.
6. Roll out: component version published to library; compatible tenants receive the change through the Blueprint path (diff, preview, apply, rollback); tenants needing a decision get a notice in chat and notifications; the team review gate applies to changes touching compliance.
7. Verify: regression suite and sandbox pass; sample invoices checked; per-tenant rollout report.
8. Communicate: customer notice in Arabic and English with date and what changes; website compliance page updated ([../product/website.md](../product/website.md)).
9. Close: entry in register; runbook "regulation change rollout" ([../runbooks/README.md](../runbooks/README.md)).

## Register fields
ID, source URL, access date, change summary, effective date, affected countries/modules, status (SECONDARY/VERIFIED), ADR link, rollout state.
