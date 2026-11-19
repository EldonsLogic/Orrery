import type { ConsoleData, StaffClaims, TenantMeta } from './types';

/** Synthetic data only: invented tenants and staff, fixed ids, no real person or company. */
export const FIXTURE_NOW = 1_800_000_000;

export const fixtureStaffClaims: StaffClaims = {
  realm: 'staff',
  staffId: 'staff-fixture-1',
  roles: ['owner'],
  mfaSatisfied: true,
  sessionVersion: 3,
};

const TENANTS: ReadonlyArray<TenantMeta> = [
  { tenantId: 'tenant-fixture-a', name: 'Sample Trading Co', plan: 'growth', status: 'active', region: 'sa', health: 'healthy' },
  { tenantId: 'tenant-fixture-b', name: 'Example Foods', plan: 'starter', status: 'trial', region: 'ae', health: 'degraded' },
  { tenantId: 'tenant-fixture-c', name: 'Demo Stores', plan: 'growth', status: 'suspended', region: 'sa', health: 'unknown' },
  { tenantId: 'tenant-fixture-d', name: 'Test Logistics', plan: 'scale', status: 'active', region: 'eg', health: 'down' },
];

/** Times are relative to `now` so the countdown works in the preview. */
export function fixtureData(now: number = FIXTURE_NOW): ConsoleData {
  return {
    tenants: TENANTS,
    grants: [
      { grantId: 'grant-fixture-1', staffId: 'staff-fixture-1', tenantId: 'tenant-fixture-a', reason: 'Investigate a slow sync reported on the ticket.', scope: ['diagnostics'], requestedAt: now - 1800, duration: 3600, status: 'approved', approvedBy: 'person-fixture-1', approvedAt: now - 1500, expiresAt: now + 2100 },
      { grantId: 'grant-fixture-2', staffId: 'staff-fixture-2', tenantId: 'tenant-fixture-b', reason: 'Check the onboarding configuration.', scope: ['configuration', 'diagnostics'], requestedAt: now - 600, duration: 1800, status: 'pending' },
      { grantId: 'grant-fixture-3', staffId: 'staff-fixture-1', tenantId: 'tenant-fixture-d', reason: 'Review the failed import.', scope: ['audit_log'], requestedAt: now - 86_400, duration: 7200, status: 'revoked', approvedBy: 'person-fixture-2', approvedAt: now - 86_000, expiresAt: now - 78_800 },
    ],
    audit: [
      { seq: 1, at: now - 86_400, action: 'support.request', decision: 'allow', code: 'OK', realm: 'staff', subject: 'staff-fixture-1', tenant: 'tenant-fixture-d', detail: '' },
      { seq: 2, at: now - 86_000, action: 'support.granted', decision: 'allow', code: 'OK', realm: 'staff', subject: 'staff-fixture-1', tenant: 'tenant-fixture-d', detail: 'grant-fixture-3' },
      { seq: 3, at: now - 80_000, action: 'support.revoke', decision: 'allow', code: 'OK', realm: 'customer', subject: 'person-fixture-2', tenant: 'tenant-fixture-d', detail: 'grant-fixture-3' },
      { seq: 4, at: now - 1800, action: 'support.request', decision: 'allow', code: 'OK', realm: 'staff', subject: 'staff-fixture-1', tenant: 'tenant-fixture-a', detail: '' },
      { seq: 5, at: now - 1500, action: 'support.granted', decision: 'allow', code: 'OK', realm: 'staff', subject: 'staff-fixture-1', tenant: 'tenant-fixture-a', detail: 'grant-fixture-1' },
      { seq: 6, at: now - 900, action: 'support.access', decision: 'deny', code: 'IDN-044', realm: 'staff', subject: 'staff-fixture-1', tenant: 'tenant-fixture-a', detail: 'grant-fixture-1' },
      { seq: 7, at: now - 600, action: 'support.request', decision: 'allow', code: 'OK', realm: 'staff', subject: 'staff-fixture-2', tenant: 'tenant-fixture-b', detail: '' },
    ],
  };
}
