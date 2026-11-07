# ADR-0007: Identity model

Status: Proposed
Owner: eldon
Approved by: pending (Eldon to approve; partner review pending, GOV-013). Proposal written for PLT-002, log 2026-11-07-eldon-claude-code-identity-adr.

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
5. **Standard protocol, replaceable provider.** OpenID Connect between the identity service and our apps. The identity provider behind it is chosen in a short spike before PLT-005 (criteria: runs in-country, open-source licence we can use as SaaS, MFA and passkeys, Arabic login screens we fully control, organisations or memberships, audit export). Candidates, licences UNVERIFIED until LEG-004 records them: Keycloak, Ory (Kratos and Hydra), or a thin service of our own over a standard library. No managed foreign IdP for customer identities while residency is unclear (Q-14). Spike acceptance criteria: no IdP marker in customer-visible paths, headers or cookies (ADR-0016); login screens are ours, built from tokens in both themes and both directions, with tenant login-page branding (ADR-0014); origin and cookie scope documented.
6. **MFA.** Mandatory for roles with `isAdmin`, for finance and accounting functions and for all staff; offered to everyone; a tenant owner may require it for all members. Checked when a token for a tenant is issued and when such a role is granted; admin-kind tools (Blueprint change requests, approvals) require a fresh step-up. Passkeys preferred, TOTP as fallback.
7. **Staff are separate.** Staff identities live in a separate realm with its own issuer and audience; a staff token is never accepted as a customer token. Staff reach a tenant only through a just-in-time support grant approved by that tenant's owner or an admin (reason, scope, expiry, tenant-visible audit; PLT-019, SEC-008). Until PLT-019 exists, staff have no access to tenant data. Staff reading in-country data from abroad is a cross-border question for counsel (Q-14).
8. **Enterprise SSO later.** A tenant may later federate its own IdP (SAML or OIDC) for its members; out of scope until a customer needs it.
9. **Where the person-to-role assignment lives.** The Blueprint defines roles; which member holds which role is runtime data stored per tenant (in the tenant's site, written only by the membership screens or an approved chat action by a role with invite permission). The gateway reads it per request; the shadow engine user is re-synced immediately on every assignment change, not only on apply, so the engine never enforces a stale copy. Tool API section 4 step 2 ("load the caller's roles from identity") is read as "from the tenant's assignment store"; the wording is fixed in the next Tool API ADR.
10. **Tokens.** Access tokens live minutes (target 5-15), are refreshed with a rotating refresh token, and every call also checks a per-membership session version so removal, suspension or compromise revokes access at once (fail closed). In the browser the session is an HttpOnly, Secure, SameSite cookie scoped to one host, never readable by JavaScript. The tenant from the subdomain must equal the token's tenant claim, or the request is rejected. Tokens carry the authentication method and time so MFA can be checked per tenant.
11. **Engine calls as the real user.** The gateway holds one impersonation credential per tenant site, stored per site and rotated, usable only for that site's shadow users. Shadow users have no password, no API key and no email delivery; engine-originated emails are disabled (ADR-0016). The engine evaluates permissions as the shadow user (threat T36).
12. **Invites and recovery.** Invites are single-use, expire, are bound to a verified email or phone, and can be created only by roles with invite permission. MFA-mandatory users and staff never recover through SMS alone; owner break-glass recovery has a delay and notifies the tenant's other admins.
13. **Deletion.** Removing a member deletes the membership and disables the shadow engine user in that tenant; tenant records keep the person's display name for audit. Deleting a person removes credentials and memberships; tenants keep their audit trail. Exact retention follows DAT-001.

## Alternatives rejected
- **Per-tenant users (option B).** Strongest isolation story and simple per-tenant deletion, but an accountant with ten clients has ten passwords and ten MFA setups, compromised accounts cannot be seen across tenants, and every security control is repeated per tenant. It works against the accountant channel, which is core to go-to-market.
- **Use the engine's own users and login.** Breaks engine invisibility (ADR-0016), ties identity to the engine we want replaceable (ADR-0002), and repeats option B.
- **Managed third-party IdP from day one.** Fast, but customer identities and login logs would sit outside the country with an unclear legal position (PDPL); revisit when hosting is chosen.
- **Roles inside the token.** Simpler checks, but stale after a Blueprint change and invites caller-supplied roles; rejected for the request-time lookup.

## Trade-offs (be clear about what A costs)
- The central store is a high-value target: one breach touches every tenant's login. Mitigation: no business data in it, MFA, passkeys, rate limits, anomaly alerts, its own penetration test before G3.
- Cross-tenant mistakes move into one layer (token audience and tenant claim). Mitigation: isolation tests in CI (SEC-004): token from tenant X against tenant Y, subdomain confusion, IDOR, cache keys.
- Shadow engine users add a sync step on every membership change; drift is a security bug, so the compiler reconciles them on every apply.
- Availability: an identity outage locks every tenant out of new sign-ins. Existing sessions continue until their access token expires; the identity service needs its own uptime target and runbook.
- Running our own IdP is real operational work (upgrades, key rotation, backups). A managed one is cheaper to run but conflicts with residency for now.

## Consequences
- If accepted: PLT-005 builds the identity service as above; WEB-003 builds sign-in and the workspace switcher on it; ERP-008 maps memberships and Blueprint roles to engine users; SEC-004 adds the isolation tests; the identity-provider spike is part of PLT-005.
- The Tool API (contracts/tool-api.md) keeps resolving role and scope per call from the session; no contract change is needed now.
- Acceptance needs: both founders set `Approved by` and `Status: Accepted`, and a security review by a different model or founder is recorded (RULES 42). A first cross-model review (2026-11-07) raised the points now in items 6-12 and Q-14.
- Open question Q-1 closes with this ADR when accepted; Q-14 (where the identity store lives across three countries) stays open and must be answered before PLT-005 stores real users.
- Tenant lifecycle hooks: suspension blocks token issuance for that tenant and bumps every session version; export and delete remove memberships and shadow users (erasure of names in tenant records follows DAT-001).

## Supersedes
none
