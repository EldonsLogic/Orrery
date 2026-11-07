# ADR-0007: Identity model

Status: Accepted
Owner: eldon
Approved by: Eldon and partner

## Context
Sign-in must be decided before the app shell (WEB-003) and the identity service (PLT-005) are built, and it is a G0 exit criterion. Facts that shape it:
- One person often works for several companies: an owner with two companies, an outside accountant with ten clients (the accountant channel), an auditor. Open question Q-1.
- Each tenant is its own engine site with its own database (ADR-0006). The engine is invisible (ADR-0016): customers never see its login page, cookies or user screens.
- Roles, functions and scopes live in each tenant's Blueprint and are generated on apply; the chat acts with the user's own permissions and roles never come from the request (ADR-0004, AGENTS.md security rules).
- Our staff need audited, just-in-time support access, separate from customer identities.
- Customer data stays in-country (ADR-0006); hosting is not chosen yet (INF-001).
Options compared in [tenancy-and-identity](../architecture/tenancy-and-identity.md).

## Decision
PROPOSED, recommended: **central identity with per-tenant membership and roles** (option A).
1. **One account per person, held centrally.** The identity service (PLT-005) owns login, password and passkey, MFA, sessions, devices and recovery. It holds no tenant business data: only the person (name, verified email or phone, credentials, MFA factors) and a membership list (tenant id, status, invited by, when).
2. **Authorisation stays in the tenant.** Membership says only "this person may enter this tenant". What they may do comes from the roles assigned in that tenant's Blueprint, resolved at request time by the gateway and the Tool API, and failing closed when the lookup fails. Tokens never carry roles or permissions.
3. **One token per tenant.** After sign-in the person picks a workspace; the service issues a short-lived token whose tenant claim and audience name that one tenant. Switching workspace issues a new token. Every service re-derives the tenant from the token, never from the URL, body or a header (tenancy-and-identity, Routing rule 3). A token for tenant X is rejected by tenant Y.
4. **The engine never authenticates customers.** Engine login is disabled for customer users. On apply, the compiler provisions one engine user per membership in that tenant's site (a shadow user carrying the Blueprint roles); the gateway calls the engine as that user. Engine passwords are never set or shown.
5. **Standard protocol, replaceable provider.** OpenID Connect between the identity service and our apps. The identity provider behind it is chosen in a short spike before PLT-005 (criteria: runs in-country, open-source licence we can use as SaaS, MFA and passkeys, Arabic login screens we fully control, organisations or memberships, audit export). Candidates, licences UNVERIFIED until LEG-004 records them: Keycloak, Ory (Kratos and Hydra), or a thin service of our own over a standard library. No managed foreign IdP for customer identities while residency is unclear (Q-1 follow-up below).
6. **MFA.** Mandatory for roles with `isAdmin`, for finance and accounting functions and for all staff; offered to everyone. Passkeys preferred, TOTP as fallback; SMS only as a last recovery path.
7. **Staff are separate.** Staff identities live in a separate realm with mandatory MFA. They reach a tenant only through a just-in-time support grant (reason, approver, scope, expiry, tenant-visible audit; PLT-019, SEC-008).
8. **Enterprise SSO later.** A tenant may later federate its own IdP (SAML or OIDC) for its members; out of scope until a customer needs it.
9. **Deletion.** Removing a member deletes the membership and disables the shadow engine user in that tenant; tenant records keep the person's display name for audit. Deleting a person removes credentials and memberships; tenants keep their audit trail. Exact retention follows DAT-001.

## Alternatives rejected
- **Per-tenant users (option B).** Strongest isolation story and simple per-tenant deletion, but an accountant with ten clients has ten passwords and ten MFA setups, compromised accounts cannot be seen across tenants, and every security control is repeated per tenant. It works against the accountant channel, which is core to go-to-market.
- **Use the engine's own users and login.** Breaks engine invisibility (ADR-0016), ties identity to the engine we want replaceable (ADR-0002), and repeats option B.
- **Managed third-party IdP from day one.** Fast, but customer identities and login logs would sit outside the country with an unclear legal position (PDPL); revisit when hosting is chosen.
- **Roles inside the token.** Simpler checks, but stale after a Blueprint change and invites caller-supplied roles; rejected for the request-time lookup.

## Trade-offs (be clear about what A costs)
- The central store is a high-value target: one breach touches every tenant's login. Mitigation: no business data in it, MFA, passkeys, rate limits, anomaly alerts, its own penetration test before G3.
- Cross-tenant mistakes move into one layer (token audience and tenant claim). Mitigation: isolation tests in CI (SEC-004): token from tenant X against tenant Y, subdomain confusion, IDOR, cache keys.
- Shadow engine users add a sync step on every membership change; drift is a security bug, so the compiler reconciles them on every apply.
- Running our own IdP is real operational work (upgrades, key rotation, backups). A managed one is cheaper to run but conflicts with residency for now.

## Consequences
- If accepted: PLT-005 builds the identity service as above; WEB-003 builds sign-in and the workspace switcher on it; ERP-008 maps memberships and Blueprint roles to engine users; SEC-004 adds the isolation tests; the identity-provider spike is part of PLT-005.
- The Tool API (contracts/tool-api.md) keeps resolving role and scope per call from the session; no contract change is needed now.
- G0 exit criterion "identity ADR accepted" is met once both founders set `Approved by` and the status to Accepted.
- Open question Q-1 closes with this ADR when accepted.

## Supersedes
none
