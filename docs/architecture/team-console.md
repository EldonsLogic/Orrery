# Team console (PLT-012)

Status: draft
Owner: eldon

The internal, staff-only back office. UI shell and model layer only, with synthetic fixtures; nothing is connected to the identity service yet. Code: `web/app/src/console/` (pure models), `web/app/src/components/console/` (screens), routes under `web/app/src/app/(staff)/console/` (`/console/`, `/console/grants/`, `/console/audit/`). Related: ADR-0007 (identity realms), ADR-0027, ADR-0032, [tenancy and identity](tenancy-and-identity.md).

## What staff can and cannot see
- Can see without a grant: tenant metadata only, namely company name, plan, status, region and health. The tenant list projects those six fields by allow-list, so extra source fields never reach the screen. Search matches name and tenant id only.
- Cannot see without an approved grant: any customer business data (records, people, money, documents). No console screen shows it. After an approved grant the console only shows the banner; the tenant data screens arrive with PLT-019.
- The console has its own session (`staffSession.ts`): staff realm claims only, MFA satisfied, session version equal to the current one from identity (a missing current version counts as stale, fail closed) and a known staff role. Anything else renders only a denial reason, with no navigation and no data. A customer sign-in cannot open it.
- Roles (deny by default, `access.ts`): `support` (tenants, own grants, own audit, request), `tenant_admin_staff` (all grants and audit, request), `security` (all grants and audit, no request), `owner` (everything staff may do: tenants, all grants and audit, request). No staff role can approve or revoke. Unknown roles and malformed lists grant nothing.
- UNDECIDED AUTH DESIGN: the four staff roles and this permission table are a UI-only proposal. Identity has no staff role claim yet. They need an ADR and a security review before this console is accepted (Q-225 b); until then they are not an authorization decision.

## Grant flow
Staff request access to one tenant with a reason, scope and duration (same limits as identity: reason up to 500 characters, up to 240 minutes, five pending per staff member and tenant, open tenants only). A pending request lapses after 24 hours. Only a tenant owner or admin approves or revokes, with a fresh MFA step-up in the customer realm (identity and ADR-0007 point 7); staff cannot, so pending rows read "Awaiting tenant approval" and the console has no approve or revoke buttons. Approved grants count down and end on their own, or earlier on revoke. States on screen: pending, approved (with countdown), revoked, expired, lapsed.
Only the request action goes through `SupportGrantPort` (`port.ts`); the port has no approve or revoke. The placeholder returns a fixed "not wired" result, executes nothing, stores nothing and logs nothing. The identity service wiring replaces it in PLT-019 (with SEC-008).
Entering a tenant needs a live approved grant of that staff member for that tenant; the banner then states the tenant, scope and time left (it turns to a danger tone under ten minutes). When the grant expires or is revoked the banner and the stay end.

## Audit
The audit viewer lists grant and access events (request, approval, grant, revoke, access check), newest first, filterable by tenant, actor and action. `support` sees only its own entries. The event shape mirrors identity's `AuditEvent` (ids, decision, code; no secrets, tokens or contact data). Every console view calls `port.auditView(screen)`, which returns a promise: a screen (and entering a tenant) shows data only after it resolves and shows none if it rejects (`guard.ts`, tested with a spy port). The placeholder records nothing, and the real gateway must record the view before it returns data.

## UI rules
Tokens only, logical CSS properties, every string through next-intl (`console` namespace in `en.json` and `ar.json`; Arabic unreviewed, ADR-0033). The console may be English-first; the language switch is in its top bar. The only thing kept in the browser is the language preference (written by the existing settings provider); no claims or data are stored. The shell reuses `src/ui` components.

## Deferred
- PLT-013: human review queue (`team_reviewed` gate) and PLT-014 factory review screens, as further console sections.
- PLT-016: feature flags screen.
- PLT-019: real grant actions, tenant data views under a grant, gateway read endpoints, durable audit.
- Staff sign-in page, real session and route protection (the static export has only a client check; the gateway and identity are the boundary, Q-195).
