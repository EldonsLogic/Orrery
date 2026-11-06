# Incident response

Status: draft
Owner: eldon

Plan before the first paying customer (G3). Regulatory notification duties and deadlines under PDPL (KSA/UAE) and to customers: UNVERIFIED, research needed ([../compliance/data-protection-and-residency.md](../compliance/data-protection-and-residency.md)).

## Severity
| Sev | Definition | Response target (TBD) |
|---|---|---|
| 1 | Confirmed data exposure, cross-tenant access, signing key compromise, ledger corruption, full outage | Immediate, all hands |
| 2 | Partial outage, e-invoice submission failing, suspected exposure, failed backup | Same day |
| 3 | Degraded feature, no data risk | Next working day |

## Process
1. Detect: alert, customer report, researcher report (security.txt), team member.
2. Triage: assign incident lead, severity, open an incident log (time, facts, actions).
3. Contain: revoke keys/sessions, suspend tenant or feature, block access, preserve evidence.
4. Assess: what data, which tenants, which region, which time window (from audit log).
5. Eradicate and recover: fix, restore from tested backup if needed, verify integrity.
6. Notify: affected tenants (as owner of data), regulators where required (UNVERIFIED), processors; use pre-approved templates in Arabic and English.
7. Review: blameless post-incident review within a set time, actions into [../PLAN.md](../PLAN.md), update threat model and runbooks.

## Roles
Incident lead, communications lead, technical lead; at two founders, one person holds two roles and an external adviser is named in advance.

## Scenarios to rehearse
Leaked API key; cross-tenant read bug; ZATCA key compromise; LLM provider incident; malicious upload; compromised founder account; prompt-injection led action.

## Contacts
Security contact address, security.txt, and status page are published on the website ([../product/website.md](../product/website.md)). Runbook: see [../runbooks/README.md](../runbooks/README.md).
