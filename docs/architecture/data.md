# Data architecture

Status: draft
Owner: eldon

Where data lives, who owns it, how it is isolated and moved. Basis: [strategy 05](../strategy/05-hosting-and-data.md). Many legal points are UNVERIFIED (PDPL transfer rules, NCA scope); legal review required. Hosting rules: [security/hosting-rules](../security/hosting-rules.md).

## Stores
| Store | Contents | Isolation |
|---|---|---|
| Engine site database (per tenant) | Ledger, documents, stock, parties, users' engine permissions | One database per tenant; no cross-site queries |
| Tenant file storage | Attachments, generated PDFs, brand assets, import staging | Per-tenant prefix/bucket, per-tenant keys |
| Control-plane database | Tenants, memberships, plans, entitlements, usage, flags, brand asset records, build states | Row-level `tenant_id`; tenant id from authenticated context only |
| Blueprint store | Blueprint revisions, diffs, change sets | Per tenant, versioned; platform reads for metrics (no business records) |
| Event/audit store | Event stream ([events](../../contracts/events.md)) | Per-tenant partition and key; immutable |
| Operate store | Chat sessions, agent runs, memory | Per tenant |
| Secrets vault | Connector tokens, provider keys, per-tenant data keys | Per-tenant namespaces; no secrets in Blueprint, events or logs |
| Platform data | Component registry, templates, eval sets, reuse metrics | No customer data |

## Principles
1. **Tenant isolation first.** Tenant id is set by the platform, never trusted from payloads. Isolation tests in CI.
2. **In-country placement.** KSA tenants in a KSA region, UAE in a UAE region, Egypt decided with its legal review (provider availability UNVERIFIED).
3. **Encryption.** In transit everywhere; at rest with envelope encryption and per-tenant data keys; key deletion is the basis of verified erasure.
4. **Backups.** Daily encrypted per-tenant backups, restore drills scheduled; retention set with legal.
5. **Minimum to models.** Ids and aggregates where possible, redaction of names, IBANs, national IDs and phone numbers before model calls; no training on customer data.
6. **No raw cross-tenant learning.** Only generalised, anonymised patterns are promoted ([component-library](component-library.md)). Contract has an anonymised-reuse clause (drafted with counsel).
7. **Dates canonical.** Gregorian ISO/UTC ([calendars-and-locale](calendars-and-locale.md)); money as decimal plus currency, never float.

## Data ownership (to be put in the contract)
Client owns its business data with one-click full export (database dump, CSV, documents, Blueprint, events). Client owns its configuration output as an export; we hold a licence to reuse anonymised patterns. Every AI action is auditable per tenant.

## Classification
`business`, `personal`, `financial`, `operational` (the `data_class` in events). Personal and financial data get stricter logging and redaction.

## Lifecycle
Trial to active to suspended to exported to deleted ([tenancy-and-identity](tenancy-and-identity.md)). Deletion erases data and keys, verifies, and keeps only what law requires (set with legal).

## Staging for imports
Connector output lands in a per-tenant staging area with expiry; nothing reaches the engine until mapping is approved and validated ([connector interface](../../contracts/connector-interface.md)).

## Open questions
1. Cross-border transfer basis for LLM processing (UNVERIFIED).
2. Retention periods for audit events and backups by country.
3. Whether a local entity is required to host KSA data.
4. Search/vector indexes: per-tenant index design and deletion guarantees.

Plan IDs: DAT, INF, SEC, LEG.
