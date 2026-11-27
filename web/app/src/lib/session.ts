/**
 * Session view-model for the app shell (WEB-003). The shapes mirror what identity issues
 * (services/control-plane/identity, ADR-0007): one central person, a membership per tenant and one
 * access token per tenant, so the claims below belong to ONE tenant. Roles live in the tenant
 * token, not in the identity store. PLACEHOLDER until the real auth wiring (PLT-009 gateway plus
 * the token exchange): the fixture below is synthetic, nothing is stored, no network, no cookie.
 */
export type SessionClaims = {
  personId: string;
  tenantId: string;
  /** Role ids defined by the tenant's Blueprint; deny by default when empty. */
  roles: ReadonlyArray<string>;
  /** True only when this token's sign-in satisfied MFA (identity `mfa_satisfied`). */
  mfaSatisfied: boolean;
  /** Bumped by identity to revoke every older token for this membership. */
  sessionVersion: number;
};

export type WorkspaceMembership = {
  tenantId: string;
  /** Tenant display name (data, not UI copy). */
  name: string;
  status: 'active' | 'suspended';
  /** BPL-020 build state of the tenant's Blueprint, for the plan status in the navigation. */
  buildState?: string;
};

export type SessionState =
  | { status: 'loading' }
  | { status: 'signedOut' }
  | { status: 'error' }
  | { status: 'ready'; displayName: string; claims: SessionClaims; memberships: ReadonlyArray<WorkspaceMembership> };

export type SwitchResult = { ok: true; claims: SessionClaims } | { ok: false };
export type SwitchWorkspaceHandler = (current: SessionClaims, tenantId: string) => Promise<SwitchResult>;
export type SignOutHandler = () => Promise<void>;

// Synthetic fixture: invented names and ids; roles exist in the records fixture Blueprint.
const FIXTURE_MEMBERSHIPS: ReadonlyArray<WorkspaceMembership> = [
  { tenantId: 'tenant-fixture-a', name: 'Sample Trading Co', status: 'active', buildState: 'live' },
  { tenantId: 'tenant-fixture-b', name: 'Example Foods', status: 'active', buildState: 'built_in_sandbox' },
  { tenantId: 'tenant-fixture-c', name: 'Demo Stores', status: 'suspended', buildState: 'draft' },
];
const FIXTURE_ROLES: Readonly<Record<string, ReadonlyArray<string>>> = {
  'tenant-fixture-a': ['sales_rep'],
  'tenant-fixture-b': ['owner'],
  'tenant-fixture-c': ['accountant'],
};

const fixtureClaims = (tenantId: string): SessionClaims => ({
  personId: 'person-fixture-synthetic',
  tenantId,
  roles: FIXTURE_ROLES[tenantId] ?? [],
  mfaSatisfied: tenantId === 'tenant-fixture-b',
  sessionVersion: 1,
});

export const fixtureSession: SessionState = {
  status: 'ready',
  displayName: 'Sample Person',
  claims: fixtureClaims('tenant-fixture-a'),
  memberships: FIXTURE_MEMBERSHIPS,
};

/** PLACEHOLDER: the real handler asks identity for a token for the other tenant (one token per tenant). */
export const placeholderSwitchWorkspace: SwitchWorkspaceHandler = async (_current, tenantId) => {
  const m = FIXTURE_MEMBERSHIPS.find((x) => x.tenantId === tenantId);
  return m && m.status === 'active' ? { ok: true, claims: fixtureClaims(tenantId) } : { ok: false };
};

/** PLACEHOLDER: the real handler revokes the refresh family at identity and clears the token. */
export const placeholderSignOut: SignOutHandler = async () => undefined;

/** The caller the record screens take, derived from the claims (never read from the browser). */
export const callerOf = (claims: SessionClaims): { roleIds: ReadonlyArray<string> } => ({ roleIds: claims.roles });
