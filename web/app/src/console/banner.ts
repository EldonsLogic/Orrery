import { liveGrantFor } from './grants';
import type { GrantRecord, TenantMeta } from './types';

export const LOW_TIME_SECONDS = 10 * 60;

export type GrantBanner = {
  tenantId: string;
  tenantName: string;
  grantId: string;
  scope: ReadonlyArray<string>;
  remaining: number;
  low: boolean;
};

/** Shown only while the staff member is in a tenant AND a live approved grant for them covers it. An expired or revoked grant removes it, and with it the right to be in the tenant. */
export function buildGrantBanner(
  grants: ReadonlyArray<GrantRecord>,
  tenants: ReadonlyArray<TenantMeta>,
  staffId: string,
  activeTenantId: string | null,
  now: number,
): GrantBanner | null {
  if (!activeTenantId) return null;
  const g = liveGrantFor(grants, staffId, activeTenantId, now);
  if (!g) return null;
  const remaining = Math.max(0, (g.expiresAt as number) - now);
  return {
    tenantId: g.tenantId,
    tenantName: tenants.find((t) => t.tenantId === g.tenantId)?.name ?? g.tenantId,
    grantId: g.grantId,
    scope: g.scope,
    remaining,
    low: remaining <= LOW_TIME_SECONDS,
  };
}
