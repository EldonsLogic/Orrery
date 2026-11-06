# Hosting rules

Status: draft
Owner: eldon

Basis: [../strategy/05-hosting-and-data.md](../strategy/05-hosting-and-data.md). All legal points are UNVERIFIED until counsel reviews ([../compliance/data-protection-and-residency.md](../compliance/data-protection-and-residency.md)). Providers are not chosen; shortlist comes from the spike.

| Area | Rule |
|---|---|
| Environments | dev, staging, prod; separate accounts/projects, credentials and data |
| Placement | KSA tenants in a KSA-located region, UAE tenants in a UAE region; region is a tenant attribute set at creation; moving region is a controlled migration |
| Isolation | Site/database per tenant, separate storage prefix, per-tenant keys; shared app workers, AI layer and control plane |
| IaC only | All infrastructure from code in `infra/`, reviewed by PR; no manual production changes; drift detection; emergency change logged and back-ported to code |
| Production data | Never copied outside production; dev and staging use anonymised or synthetic data only; no developer laptops hold production data |
| Backups | Daily encrypted backups per tenant, stored in the same country; restore test on a schedule with a logged result; retention period TBD |
| Encryption | In transit TLS 1.2+; at rest everywhere; envelope keys per tenant; KMS in-region |
| Key management | Keys in managed KMS, rotation policy, no keys in code, access logged, signing keys (ZATCA) held separately with stricter access |
| Logging | Central, region-local; no secrets and minimal personal data; access-controlled; retention period TBD; audit logs immutable |
| Monitoring | Availability, errors, cost, auth anomalies, tenant-boundary violations; on-call rota defined by G3 |
| Patching | Base images and dependencies updated on a cadence; critical fixes out of band; SLAs TBD |
| Change management | PR -> CI -> staging -> approval -> prod; release notes; rollback plan; maintenance windows announced on status page |
| Network | Private networks, least-open ports, WAF/CDN at the edge, egress allow-list for services (limits SSRF/exfiltration) |
| Environments parity | Same IaC modules in all environments; versions pinned (Frappe/ERPNext/HRMS set recorded) |

## Development hosts (ADR-0018, Proposed)
Development and preview hosts (a web preview host such as Vercel, a small shared dev server) may sit outside the country because they hold **synthetic data only**. Production or pilot data never goes to a dev host; production stays in-country (ADR-0006). Dev hosts sit behind a login, keep secrets in their own secret stores (never the repo), and obey engine invisibility (browser talks only to our web app and gateway). Regions and terms of any dev host are unchecked (UNVERIFIED) until chosen.

## Third-party processor approval list
No processor is used for tenant data until it is on the list with: purpose, data class, region, DPA, security review, exit plan. Initial list: empty (TBD at G1).
| Processor | Purpose | Max data class | Region | DPA | Status |
|---|---|---|---|---|---|
| (cloud provider KSA) | Hosting | C3 | KSA | needed | to choose |
| (cloud provider UAE) | Hosting | C3 | UAE | needed | to choose |
| (LLM providers) | Model inference | C2/C3 minimised | per rules below | needed | to choose |
| (email/SMS/OTP) | Notifications | C3 (phone, email) | TBD | needed | to choose |
| (malware scanning) | Upload scanning | C2 | TBD | needed | to choose |
| (UAE accredited e-invoicing provider) | Peppol delivery | C2 | UAE | needed | to choose |

## LLM provider rules
| Rule | Detail |
|---|---|
| No training | Provider terms must exclude training on our or tenants' data; verify per provider, in writing |
| Retention | Zero or minimum retention; abuse-monitoring retention disclosed; stated in the list above |
| Regions | Gateway routes KSA tenants only to approved endpoints; whether providers offer in-region inference is UNVERIFIED; if cross-border processing is restricted, self-hosting trigger moves forward ([../strategy/06-model-strategy.md](../strategy/06-model-strategy.md)) |
| Minimisation | Send IDs and aggregates where possible; redact names, IBANs and national IDs when the task allows |
| Hidden models | Customers never see model names; provider fallback logged |
| Logging | Prompts and outputs logged per tenant in-region, same class as source data |
| Keys | One key per environment, held in the gateway only, never client-side |

## Data export and deletion SLAs
TBD (research needed, counsel). Targets to set: export delivery time, deletion time after termination, backup purge time, retention holds for tax records (periods UNVERIFIED in [../compliance/country-matrix.md](../compliance/country-matrix.md)).
