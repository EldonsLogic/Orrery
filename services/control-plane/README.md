# services/control-plane

Status: draft
Owner: unassigned

Purpose: tenant registry and lifecycle, identity, plans and entitlements, metering and billing, team console (review queue, component factory queue, just-in-time support access), audit store, feature flags, country pack rollout. Spec: [05-platform](../../docs/specs/05-platform.md), design: [tenancy-and-identity](../../docs/architecture/tenancy-and-identity.md).

**Empty until gate G1** (tenant creation scripted by G1; team console by G2).

## Identity core (PLT-005)
Package [`identity/`](identity/) holds the domain logic of [ADR-0007](../../docs/decisions/ADR-0007-identity.md), Python 3.12, standard library only. No network server, no identity provider and no real users: Q-14 blocks storing real users, and the provider and production signing come from the identity-provider spike.
- `models.py`: Person, Membership (status, session version, MFA flag), StaffIdentity in a separate realm, invites, refresh records, support grants.
- `tokens.py` + `signing.py`: short-lived access tokens (person, one tenant, audience naming that tenant, issuer, realm, session version, MFA, auth time, expiry; no roles). Algorithm pinned to the realm's signer, `none` refused, header and claim set exact, constant-time signature check, injected clock. `TestOnlyHmacSha256Signer` is for tests only.
- `service.py`: token issue and verify per realm, per-membership session version (removal, suspension, compromise and tenant suspension revoke at once), refresh rotation with reuse detection that revokes the family, MFA at issue and on role grant, owner-only "MFA for all".
- `policy.py`: roles come only from an injected `RoleResolver` (the tenant's assignment store); any unexpected result denies. MFA mandatory for `isAdmin`, finance, accounting, owner and all staff.
- `invites.py`: single-use, expiring, bound to a channel the accepting person has verified; needs the `member.invite` permission passed in as data.
- `support.py`: staff just-in-time grants, time-boxed, approved by the tenant's owner or admin with a fresh MFA step-up, never self-approved, tenant-visible audit.
- `audit.py`: append-only in-memory decisions (allow/deny, IDN code); `repository.py`: abstract store plus an in-memory test store.
Errors are `IdentityError` with codes IDN-001 to IDN-051 ([`errors.py`](identity/errors.py)); messages never carry secrets. Open points: Q-147 to Q-151 in [open-questions](../../docs/open-questions.md).

Tests: `uv run --no-project --with pytest python -W ignore -m pytest services/control-plane/tests -q`
