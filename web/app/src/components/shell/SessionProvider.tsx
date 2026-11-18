'use client';

import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';
import {
  fixtureSession,
  placeholderSignOut,
  placeholderSwitchWorkspace,
  type SessionState,
  type SignOutHandler,
  type SwitchWorkspaceHandler,
} from '../../lib/session';

type SessionApi = {
  session: SessionState;
  /** True while a token for another tenant is being fetched. */
  switching: boolean;
  /** True after a switch was refused; cleared by the next attempt or `dismissError`. */
  switchFailed: boolean;
  switchWorkspace: (tenantId: string) => Promise<void>;
  dismissError: () => void;
  signOut: () => Promise<void>;
  /** Re-reads the session; the placeholder just returns to the fixture. */
  retry: () => void;
};

const SessionContext = createContext<SessionApi | null>(null);

export function useSession(): SessionApi {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error('useSession outside SessionProvider');
  return ctx;
}

export type SessionProviderProps = {
  children: ReactNode;
  /** Tests and the real wiring pass these; the defaults are the synthetic placeholders. */
  initial?: SessionState;
  onSwitch?: SwitchWorkspaceHandler;
  onSignOut?: SignOutHandler;
};

/**
 * PLACEHOLDER session source. REAL AUTH WIRING GOES HERE: read the tenant token from the identity
 * client, expose its claims as SessionState, and exchange tokens on workspace switch. The state
 * lives in memory only; nothing is written to storage or cookies (only the theme and language
 * preferences are, by their own hooks).
 */
export function SessionProvider({
  children,
  initial = fixtureSession,
  onSwitch = placeholderSwitchWorkspace,
  onSignOut = placeholderSignOut,
}: SessionProviderProps) {
  const [session, setSession] = useState<SessionState>(initial);
  const [switching, setSwitching] = useState(false);
  const [switchFailed, setSwitchFailed] = useState(false);

  const switchWorkspace = useCallback(
    async (tenantId: string) => {
      if (session.status !== 'ready' || tenantId === session.claims.tenantId) return;
      setSwitching(true);
      setSwitchFailed(false);
      try {
        const r = await onSwitch(session.claims, tenantId);
        if (r.ok) setSession({ ...session, claims: r.claims });
        else setSwitchFailed(true); // fail closed: keep the current workspace
      } catch {
        setSwitchFailed(true);
      } finally {
        setSwitching(false);
      }
    },
    [session, onSwitch],
  );

  const signOut = useCallback(async () => {
    try {
      await onSignOut();
    } finally {
      setSession({ status: 'signedOut' });
    }
  }, [onSignOut]);

  const value = useMemo<SessionApi>(
    () => ({
      session,
      switching,
      switchFailed,
      switchWorkspace,
      dismissError: () => setSwitchFailed(false),
      signOut,
      retry: () => setSession(initial),
    }),
    [session, switching, switchFailed, switchWorkspace, signOut, initial],
  );
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}
