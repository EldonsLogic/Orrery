'use client';

import { useEffect } from 'react';
import type { ViewScreen } from '../../console/port';
import { useConsole } from './ConsoleProvider';

/** Every console view is audited: tell the port once per screen mount, only for a ready session. */
export function useViewAudit(screen: ViewScreen) {
  const { port, session } = useConsole();
  const ready = session.status === 'ready';
  useEffect(() => {
    if (ready) port.auditView(screen);
  }, [ready, port, screen]);
}
