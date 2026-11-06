# Spec 05: Platform (Part 5)

Status: draft
Owner: unassigned
Plan IDs: PLT, SEC, INF, DAT (plus QA, LEG for legal items)

## Purpose
The control plane: everything needed to run many tenants safely and economically, and the internal tools our team uses to build and support them.

## Responsibilities
1. **Tenant provisioning and lifecycle**: trial, active, suspended, exported, deleted; scripted site creation, placement by country/region, key creation, backups ([tenancy-and-identity](../architecture/tenancy-and-identity.md)).
2. **Identity**: authentication, MFA for admins, SSO later; user to tenant membership; per-tenant roles (ADR-0007 proposed).
3. **Plans, entitlements, metering, billing**: everything unlocked at first, but entitlements and metering exist from day one so gating can be switched on later ([ADR-0005](../decisions/)).
4. **AI model gateway**: routing by tier, per-tenant budgets, caching, regional routing, logging, provider fallback ([ai-layer](../architecture/ai-layer.md)).
5. **Team console**: build review queue (the human gate), component factory queue, tenant list and health, audited just-in-time support access.
6. **Tenant branding storage and serving**: asset pipeline, resolved tokens ([theming](../architecture/theming.md)).
7. **Observability, feature flags, environments** (dev, staging, sandbox tenants, production).
8. **Audit store** for the event stream.
9. **Country pack registry and rollout**: which pack version each tenant runs, canary and promotion of pack upgrades (tax rates, holiday tables, announced Hijri dates), tenant placement by country ([country-packs](../architecture/country-packs.md), [calendars-and-locale](../architecture/calendars-and-locale.md)).

## Interfaces
| Contract | Use |
|---|---|
| Events | Stores audit events, aggregates `meter.*` into usage and invoices |
| Build states | Source of truth for build state and transitions |
| Tool API | Provides identity/role lookup the gateway uses (fail closed) |
| Component manifest | Entitlement and rollout decisions per component |

## Data owned
Tenant registry (including country and pinned country-pack version), memberships, plans, entitlements, usage records, invoices, feature flags, audit store, secrets vault metadata, brand asset records, support-access grants, gateway logs, backups metadata.

## Key behaviours
- Creating a tenant is one scripted, idempotent operation that either completes or leaves nothing behind.
- Entitlements are checked server-side at the feature boundary (for example white-label "Powered by" removal, custom domain, AI action allowances).
- Support access is just-in-time: reason, approver, scope, expiry, full audit, tenant-visible log.
- Export: one-click full export (database dump, CSV, documents, Blueprint, events); deletion cryptographically erases keys and verifies.
- Gateway enforces the tenant AI budget with owner alerts and a hard cap; deterministic paths keep working when budget is exhausted.

## Failure modes
| Failure | Handling |
|---|---|
| Provisioning half-done | Idempotent steps with a saga log; automatic cleanup or resume |
| Cross-tenant leak risk (bug) | Tenant id from authenticated context only; per-site DB; isolation tests in CI; incident runbook |
| Provider outage | Fallback chain in gateway; status page; degrade gracefully |
| Backup restore fails | Scheduled restore drills; alert on missed backups |
| Billing/metering drift | Events are the source; periodic reconciliation job |

## Security notes
- MFA for all internal staff; least privilege; no standing production access.
- Secrets in a vault; per-tenant envelope encryption keys.
- In-country placement of tenant data per [hosting rules](../security/hosting-rules.md) (published by the security workstream).
- Immutable audit; time-synchronised; access to the audit store is itself audited.
- Independent security test before G3.

## Open questions
1. Identity option A (central identity, per-tenant roles) vs B: ADR-0007 open; recommendation A.
2. Provider(s) and region for KSA hosting; UAE later (UNVERIFIED availability).
3. Billing provider and Saudi tax invoicing for our own subscription.
4. Do we need a local legal entity to host KSA data or sign KSA customers? (Legal.)

## Acceptance criteria
**G1 (spine proven)**
- One command creates a fresh tenant site, a tenant record, keys and a first admin; one command deletes it and verifies erasure of its secrets.
- Entitlements and metering exist as data: a feature flag can switch a gated feature on per tenant, and AI usage events aggregate into a usage record.
- Gateway routes a test call by tier, enforces a tiny budget and logs it.

**G2 (pilot-ready)**
- Pilot tenant on in-country infrastructure with daily encrypted backups and one tested restore.
- Team console supports the review gate, and a just-in-time support session is granted, used and audited.
- A country pack upgrade can be rolled to a canary tenant and rolled back.
- Observability shows tenant health, error rates and AI cost per tenant.
- Export works end to end for the pilot tenant.
