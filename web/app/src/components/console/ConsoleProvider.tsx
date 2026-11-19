'use client';

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { fixtureData, fixtureStaffClaims, FIXTURE_NOW, FIXTURE_SESSION_VERSION } from '../../console/fixture';
import { mayEnterTenant } from '../../console/guard';
import { liveGrantFor } from '../../console/grants';
import { placeholderPort, type SupportGrantPort } from '../../console/port';
import { buildStaffSessionView, type StaffSessionView } from '../../console/staffSession';
import type { ConsoleData, StaffClaims } from '../../console/types';

export type ConsoleApi = {
  session: StaffSessionView;
  data: ConsoleData;
  now: number;
  port: SupportGrantPort;
  activeTenantId: string | null;
  /** Refused (resolves false) unless a live approved grant covers the tenant AND the audit of the entry resolved. */
  enterTenant: (tenantId: string) => Promise<boolean>;
  /** Test seam: treat every view audit as already resolved (server renders run no effects). */
  assumeAudited: boolean;
  leaveTenant: () => void;
};

const Ctx = createContext<ConsoleApi | null>(null);

export function useConsole(): ConsoleApi {
  const c = useContext(Ctx);
  if (!c) throw new Error('useConsole outside ConsoleProvider');
  return c;
}

export type ConsoleProviderProps = {
  children: ReactNode;
  /** Tests and the real wiring pass these; the defaults are synthetic and the placeholder port. */
  claims?: StaffClaims | null;
  /** The current session version from identity. Missing means the session is stale (fail closed). */
  currentSessionVersion?: number;
  assumeAudited?: boolean;
  data?: ConsoleData;
  /** Fixed clock for tests. Without it the clock is live and ticks every second. */
  now?: number;
  port?: SupportGrantPort;
  initialTenantId?: string | null;
};

/**
 * PLACEHOLDER staff session source. REAL AUTH WIRING GOES HERE: verify the staff-realm token with
 * identity, expose its claims and the current session version, and load tenants, grants and audit
 * through the gateway. Claims and data are held in memory only. The one thing the browser keeps is
 * the language preference (written by the existing settings provider, not by the console).
 */
export function ConsoleProvider({
  children,
  claims = fixtureStaffClaims,
  currentSessionVersion = FIXTURE_SESSION_VERSION,
  assumeAudited = false,
  data: dataProp,
  now: nowProp,
  port = placeholderPort,
  initialTenantId = null,
}: ConsoleProviderProps) {
  const live = nowProp === undefined;
  const [now, setNow] = useState(nowProp ?? FIXTURE_NOW);
  const [data, setData] = useState<ConsoleData>(() => dataProp ?? fixtureData(nowProp ?? FIXTURE_NOW));
  const [activeTenantId, setActive] = useState<string | null>(initialTenantId);
  const session = useMemo(() => buildStaffSessionView(claims, currentSessionVersion), [claims, currentSessionVersion]);

  useEffect(() => {
    if (!live) return;
    const t0 = Math.floor(Date.now() / 1000);
    setNow(t0);
    if (!dataProp) setData(fixtureData(t0));
    const id = setInterval(() => setNow(Math.floor(Date.now() / 1000)), 1000);
    return () => clearInterval(id);
  }, [live, dataProp]);

  const enterTenant = useCallback(
    async (tenantId: string) => {
      const ok = await mayEnterTenant(port, session, data.grants, tenantId, now);
      if (ok) setActive(tenantId);
      return ok;
    },
    [session, data.grants, now, port],
  );
  const leaveTenant = useCallback(() => setActive(null), []);

  // An expired or revoked grant ends the stay (the banner model also hides itself).
  const staffId = session.status === 'ready' ? session.staffId : '';
  const stillLive = activeTenantId !== null && !!liveGrantFor(data.grants, staffId, activeTenantId, now);
  const effective = stillLive ? activeTenantId : null;
  // Once the grant is gone, forget the tenant: a later new grant must go through enterTenant (and its audit) again.
  useEffect(() => {
    if (activeTenantId !== null && !stillLive) setActive(null);
  }, [activeTenantId, stillLive]);

  const api: ConsoleApi = { session, data, now, port, activeTenantId: effective, enterTenant, leaveTenant, assumeAudited };
  return <Ctx.Provider value={api}>{children}</Ctx.Provider>;
}
