import { can } from './access';
import type { TenantHealth, TenantMeta, TenantStatus } from './types';

export type TenantFilter = { query?: string; status?: TenantStatus | ''; region?: string; health?: TenantHealth | '' };

/** Projection by allow-list: even if a source row carried more, only metadata leaves this function. */
const project = (r: TenantMeta): TenantMeta => ({
  tenantId: r.tenantId,
  name: r.name,
  plan: r.plan,
  status: r.status,
  region: r.region,
  health: r.health,
});

/** Search matches the company name and tenant id only. Needs `tenants.view`; otherwise nothing. */
export function buildTenantList(
  rows: ReadonlyArray<TenantMeta>,
  roles: ReadonlyArray<unknown>,
  filter: TenantFilter = {},
): TenantMeta[] {
  if (!can(roles, 'tenants.view')) return [];
  const q = (filter.query ?? '').trim().toLowerCase();
  return rows
    .filter((r) => !q || r.name.toLowerCase().includes(q) || r.tenantId.toLowerCase().includes(q))
    .filter((r) => !filter.status || r.status === filter.status)
    .filter((r) => !filter.region || r.region === filter.region)
    .filter((r) => !filter.health || r.health === filter.health)
    .map(project)
    .sort((a, b) => a.name.localeCompare(b.name));
}

export const regionsOf = (rows: ReadonlyArray<TenantMeta>): string[] => [...new Set(rows.map((r) => r.region))].sort();
