'use client';

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { fixtureData, fixtureStaffClaims, FIXTURE_NOW } from '../../console/fixture';
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
  /** Refused (returns false) unless a live approved grant of this staff member covers the tenant. */
  enterTenant: (tenantId: string) => boolean;
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
  data?: ConsoleData;
  /** Fixed clock for tests. Without it the clock is live and ticks every second. */
  now?: number;
  port?: SupportGrantPort;
  initialTenantId?: string | null;
};

/**
 * PLACEHOLDER staff session source. REAL AUTH WIRING GOES HERE: verify the staff-realm token with
 * identity, expose its claims, and load tenants, grants and audit through the gateway. In memory
 * only; nothing is stored in the browser.
 */
export function ConsoleProvider({
  children,
  claims = fixtureStaffClaims,
  data: dataProp,
  now: nowProp,
  port = placeholderPort,
  initialTenantId = null,
}: ConsoleProviderProps) {
  const live = nowProp === undefined;
  const [now, setNow] = useState(nowProp ?? FIXTURE_NOW);
  const [data, setData] = useState<ConsoleData>(() => dataProp ?? fixtureData(nowProp ?? FIXTURE_NOW));
  const [activeTenantId, setActive] = useState<string | null>(initialTenantId);
  const session = useMemo(() => buildStaffSessionView(claims), [claims]);

  useEffect(() => {
    if (!live) return;
    const t0 = Math.floor(Date.now() / 1000);
    setNow(t0);
    if (!dataProp) setData(fixtureData(t0));
    const id = setInterval(() => setNow(Math.floor(Date.now() / 1000)), 1000);
    return () => clearInterval(id);
  }, [live, dataProp]);

  const enterTenant = useCallback(
    (tenantId: string) => {
      if (session.status !== 'ready' || !liveGrantFor(data.grants, session.staffId, tenantId, now)) return false;
      port.auditView('tenant_banner', tenantId);
      setActive(tenantId);
      return true;
    },
    [session, data.grants, now, port],
  );
  const leaveTenant = useCallback(() => setActive(null), []);

  // An expired or revoked grant ends the stay (the banner model also hides itself).
  const staffId = session.status === 'ready' ? session.staffId : '';
  const stillLive = activeTenantId !== null && !!liveGrantFor(data.grants, staffId, activeTenantId, now);
  const effective = stillLive ? activeTenantId : null;

  const api: ConsoleApi = { session, data, now, port, activeTenantId: effective, enterTenant, leaveTenant };
  return <Ctx.Provider value={api}>{children}</Ctx.Provider>;
}
