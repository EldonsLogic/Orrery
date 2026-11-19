import { liveGrantFor } from './grants';
import type { SupportGrantPort, ViewScreen } from './port';
import type { StaffSessionView } from './staffSession';
import type { GrantRecord } from './types';

/** Record the view, then allow it. A rejected audit means the view is NOT allowed (fail closed). */
export async function auditThenAllow(port: SupportGrantPort, screen: ViewScreen, tenantId?: string): Promise<boolean> {
  try {
    await port.auditView(screen, tenantId);
    return true;
  } catch {
    return false;
  }
}

/** Entering a tenant needs a ready session, a live approved grant for that tenant, and a resolved audit of the entry. */
export async function mayEnterTenant(
  port: SupportGrantPort,
  session: StaffSessionView,
  grants: ReadonlyArray<GrantRecord>,
  tenantId: string,
  now: number,
): Promise<boolean> {
  if (session.status !== 'ready' || !liveGrantFor(grants, session.staffId, tenantId, now)) return false;
  return auditThenAllow(port, 'tenant_banner', tenantId);
}
