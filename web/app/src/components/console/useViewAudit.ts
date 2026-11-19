'use client';

import { useEffect, useState } from 'react';
import { auditThenAllow } from '../../console/guard';
import type { ViewScreen } from '../../console/port';
import { useConsole } from './ConsoleProvider';

export type ViewAuditState = 'pending' | 'ok' | 'failed';

/**
 * Every console view is audited before it shows data: the screen renders its data only when this
 * returns 'ok' (the audit resolved). A rejected audit gives 'failed' and no data. A session that is
 * not ready never calls the port.
 */
export function useViewAudit(screen: ViewScreen): ViewAuditState {
  const { port, session, assumeAudited } = useConsole();
  const ready = session.status === 'ready';
  const [state, setState] = useState<ViewAuditState>(assumeAudited ? 'ok' : 'pending');
  useEffect(() => {
    if (!ready || assumeAudited) return;
    let live = true;
    setState('pending');
    void auditThenAllow(port, screen).then((ok) => {
      if (live) setState(ok ? 'ok' : 'failed');
    });
    return () => {
      live = false;
    };
  }, [ready, port, screen, assumeAudited]);
  return ready ? state : 'pending';
}
