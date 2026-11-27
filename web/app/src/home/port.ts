import type { SessionClaims } from '../lib/session';
import { liveHome, simulatingHome } from './fixture';
import type { HomeOverview } from './types';

/**
 * The only way the home screen reads anything. REAL WIRING GOES HERE (a later row): the gateway returns the overview for
 * the caller's token, and the SERVER scopes it to the caller's roles. The fixture copies that rule: deny by default, and
 * only the owner and the accountant see money and approvals.
 */
export type HomePort = { overview: (claims: SessionClaims) => Promise<HomeOverview | null> };

const FINANCE_ROLES = ['owner', 'accountant'];

export const scopeOverview = (o: HomeOverview, roles: ReadonlyArray<string>): HomeOverview =>
  roles.some((r) => FINANCE_ROLES.includes(r)) ? o : { ...o, today: null, kpis: [], approvals: [], activity: [] };

export const fixtureHomePort: HomePort = {
  overview: async (claims) => {
    const o = claims.tenantId === 'tenant-fixture-a' ? liveHome : claims.tenantId === 'tenant-fixture-b' ? simulatingHome : null;
    return o ? scopeOverview(o, claims.roles) : null;
  },
};
