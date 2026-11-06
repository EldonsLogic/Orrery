# 05 - Hosting and data ownership

Date: 2026-11-04. Many legal points are UNVERIFIED (03-regulations flags PDPL transfer rules and NCA scope as not confirmed from official sources). Lawyer pass required.

## Recommendation
**Isolated tenant per customer on shared infrastructure, hosted in-country, operated by us.** Dedicated instances for large or regulated clients later; hybrid later.

- **Unit of isolation:** one engine site/database per tenant (matches the seed, `04`), separate object-storage prefix, per-tenant encryption keys (envelope), per-tenant backups.
- **Placement:** KSA tenants in a KSA-located cloud region; UAE tenants in a UAE region. Which providers have compliant in-country regions and whether they meet NCA controls is UNVERIFIED: ask for a provider shortlist during the spike.
- **Shared:** application workers, the AI layer, the control plane. A noisy-tenant limit per tenant (rate, token budget).
- **Cost shape (ASSUMPTION, validate):** a small tenant should cost tens of dollars per month in infra, not a VPS each. A dedicated VPS per client means per-client patching, backups and upgrades; at 100 clients that is an ops team, which is the software-house trap in infrastructure form.

## Data ownership principles (a selling point, put them in the contract)
1. The client owns its business data. One-click full export at any time (database dump, CSV, documents). No hostage-taking; this directly answers the Odoo lock-in grievance.
2. The client owns its configuration output as an export, but grants us a licence to reuse **anonymised, de-identified Blueprint patterns and components** to improve the platform. This clause is what makes the flywheel legal. Draft with counsel.
3. We do not train models on client data. Provider contracts: zero-retention / no-training terms; verify per provider.
4. Every AI action is auditable per tenant.

## LLM data flow (the real PDPL question)
- Send the minimum context: IDs and aggregates where possible; redact names, IBANs and national IDs before the call where the task allows.
- Region-aware routing in the gateway: KSA tenant traffic goes only to approved endpoints. Whether major providers offer in-Kingdom or in-region inference is UNVERIFIED.
- Whether sending business data to a foreign model API is a cross-border transfer needing a legal basis under Saudi PDPL / UAE PDPL: UNVERIFIED (03 open legal questions). If it is restricted, the open-weight self-hosting trigger in `06` moves forward for KSA.

## The original hosting options
| Option | Verdict | Reason |
|---|---|---|
| VPS per client, fully ours | **Reject** | Per-client ops; kills software margins. Containers/sites per tenant on shared infra give the same isolation story. |
| Hybrid (agents ours, ERP and data client-side) | **Later** | Distributing the engine to client premises triggers GPL distribution (04) and multiplies support. Offer only to large/regulated accounts, priced up. |
| In-country shared-infra tenant isolation | **Keep, default** | Best cost/isolation/compliance balance. |
| Fully on-premise | **Reject for v1** | Not owner-led SME. |

## Security baseline for v1 (what investors and auditors ask)
SSO/MFA for admins, role-based access in every tenant, immutable audit trail on posting and AI actions, daily encrypted backups with tested restores, secrets management, per-tenant data export/delete, incident runbook. SOC 2 / ISO 27001 are 12-24 month items; NCA cloud controls applicability: UNVERIFIED.

## Open questions
- Which in-country providers, at what price, and do they meet NCA/PDPL expectations?
- Do we need a local entity to host KSA data or sign KSA customers?
- Is cross-border LLM processing of financial data permitted, and on what basis?
