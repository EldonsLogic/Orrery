/**
 * Types for the internal team console (PLT-012). They mirror the identity service
 * (services/control-plane/identity: StaffIdentity, SupportGrant, AuditEvent) but hold METADATA only:
 * nothing here can carry customer business data. Times are Unix seconds, as in identity.
 */
export const STAFF_ROLES = ['support', 'tenant_admin_staff', 'security', 'owner'] as const;
export type StaffRole = (typeof STAFF_ROLES)[number];
export const isStaffRole = (v: unknown): v is StaffRole => typeof v === 'string' && (STAFF_ROLES as readonly string[]).includes(v);

/** Claims of a staff-realm token (separate issuer and audience from customers, ADR-0007). */
export type StaffClaims = {
  realm: string;
  staffId: string;
  roles: ReadonlyArray<string>;
  mfaSatisfied: boolean;
  sessionVersion: number;
};

export type TenantStatus = 'trial' | 'active' | 'suspended' | 'exported' | 'deleted';
export type TenantHealth = 'healthy' | 'degraded' | 'down' | 'unknown';

/** The only tenant fields staff see without a grant. No names of people, no money, no records. */
export type TenantMeta = {
  tenantId: string;
  /** Company display name chosen at sign-up (metadata, not business data). */
  name: string;
  plan: string;
  status: TenantStatus;
  /** Known markets are translated; anything else shows its raw code. */
  region: string;
  health: TenantHealth;
};

export type GrantStatus = 'pending' | 'approved' | 'revoked';
export type GrantRecord = {
  grantId: string;
  staffId: string;
  tenantId: string;
  reason: string;
  scope: ReadonlyArray<string>;
  requestedAt: number;
  duration: number;
  status: GrantStatus;
  approvedBy?: string;
  approvedAt?: number;
  expiresAt?: number;
};

export type AuditEntry = {
  seq: number;
  at: number;
  action: string;
  decision: 'allow' | 'deny';
  code: string;
  realm: 'staff' | 'customer';
  subject: string | null;
  tenant: string | null;
  detail: string;
};

export type ConsoleData = {
  tenants: ReadonlyArray<TenantMeta>;
  grants: ReadonlyArray<GrantRecord>;
  audit: ReadonlyArray<AuditEntry>;
};

/** Same limits as identity/support.py. */
export const MAX_SUPPORT_SECONDS = 4 * 3600;
export const MAX_REASON_LEN = 500;
export const PENDING_TTL = 24 * 3600;
export const MAX_PENDING = 5;
