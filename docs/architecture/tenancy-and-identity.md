# Tenancy and identity

Status: draft
Owner: eldon

Decisions: ADR-0006 (tenancy), ADR-0007 (identity, PROPOSED, open), ADR-0004 (one chat, role-based views).

## Tenancy: site per tenant on shared infrastructure
- One engine **site** (own database, own files) per customer, on shared application workers in the customer's country region. No VPS per client (per-client ops is the software-house trap).
- Shared: app workers, AI layer, control plane, web apps. Per-tenant limits: request rate, AI budget, worker share.
- Dedicated instances for large or regulated clients later; hybrid/on-prem later and a legal item (GPL distribution).

### Routing
1. **Subdomain first**: `<tenant-slug>.<product-domain>` resolves to the tenant at the edge; the slug maps to a tenant id in the control plane. The product domain is a placeholder until the name is cleared.
2. **Custom domains later**: tenant adds `erp.theircompany.com` (CNAME + verification + managed TLS); entitlement-gated; domain-to-tenant map in the control plane.
3. Tenant id is derived at the edge and re-derived from the session in services; never from request bodies.
4. Reserved slugs, homograph checks and takeover protection on custom domains.

## Identity options
| | A: central identity + per-tenant roles | B: per-tenant users |
|---|---|---|
| Model | One person record in the platform; membership per tenant; roles live in each tenant's Blueprint | Each tenant has its own user table; same person = separate accounts |
| Pros | One login for owners/accountants who work with several companies (accountant channel); MFA/SSO once; our staff identities cleanly separated; easy to revoke; single place for security events | Strongest isolation story; simpler data deletion per tenant; no shared user store to breach |
| Cons | Central store is a high-value target; cross-tenant membership logic; deletion must handle multi-tenant persons | Poor accountant experience; duplicate credentials; weak MFA coverage; hard to detect compromised users across tenants |
| Risk control | Tenant id in the token claims; roles resolved per tenant from the Blueprint at request time (fail closed); no tenant data in the identity store | Needs the same controls per tenant, repeated |
**Recommendation: A** (central identity, per-tenant roles), because the accountant and multi-company owner case is core to the channel strategy and central MFA is easier to enforce well. Keep it reversible: roles and membership are the interface; the identity provider can be swapped. ADR-0007 stays PROPOSED until Eldon and the partner approve.

## Role, function and scope model
- **Function** (what the person does): owner, general_manager, finance, accounting, sales, purchasing, warehouse, hr, operations, support, read_only, custom.
- **Role** (named bundle in the Blueprint): permissions per entity and action, field restrictions, home view, flags (`isAdmin`).
- **Scope** (which records): company, branch, warehouse, department, own_records, assigned_records.
- The engine enforces role + scope on every operation; the tool API checks first ([tool-api](../../contracts/tool-api.md)). The chat acts with the user's own permissions. A user can hold several roles; permissions union within one tenant, scopes apply per role.
- Roles are generated from the Blueprint on apply; roles never come from the client request.
- Internal staff identities are separate (staff directory with mandatory MFA); they get tenant access only through just-in-time, audited support sessions with reason, scope and expiry.

## Plans, entitlements and metering
- **Plan**: named bundle of entitlements and limits. **Entitlement**: a switch or quota checked server-side (AI allowance, users, custom domain, white-label "Powered by" removal, storage, connectors tier, retention).
- Free-first: at launch every tenant gets everything, but entitlements are assigned and checked, and usage is metered from day one, so gating can be switched on later without code changes (ADR-0005).
- Metering: `meter.*` events aggregated into usage records ([events](../../contracts/events.md)); billing later reads usage.
- Entitlement checks live at feature boundaries: branding (`whiteLabel`), domain, AI budget in the gateway, user counts at invite.

## Tenant lifecycle
`trial -> active -> suspended -> exported -> deleted`. Suspension blocks sign-in but keeps data; export produces the full export bundle; deletion erases data and keys with verification. Every transition is an event and requires specific actors (owner, billing, support-with-approval).

## Security notes
- MFA for admin roles; session binding; short-lived tokens; device/session list.
- No shared credentials between tenants; per-tenant service identities for the engine.
- Cross-tenant isolation tests: IDOR attempts, token swapping, subdomain confusion, cache key checks.

## Open questions
1. SSO for larger customers: which protocols and when.
2. Whether accountants get a firm-level console (multi-tenant view). Product question, post G2.
3. Identity provider: build on an open-source IdP vs managed service (licence and residency checks).

Plan IDs: PLT, SEC, INF.
