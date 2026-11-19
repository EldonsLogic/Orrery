import type { RequestDraft } from './grants';

/**
 * PLACEHOLDER port to the identity service (support.request, support.approve, support.revoke).
 * REAL WIRING GOES HERE (PLT-019, with SEC-008): call identity with the staff token; approve and
 * revoke are decided by a tenant owner or admin with a fresh MFA step-up, so the console only hands
 * the request over and shows the result. This placeholder NEVER executes anything: it has a fixed
 * result, stores nothing and logs nothing. Open question Q-225.
 */
export type PortResult = { ok: false; reason: 'not_wired' };
export type ViewScreen = 'tenants' | 'grants' | 'audit' | 'tenant_banner';

export type SupportGrantPort = {
  request: (draft: RequestDraft) => Promise<PortResult>;
  approve: (grantId: string) => Promise<PortResult>;
  revoke: (grantId: string) => Promise<PortResult>;
  /** Every console view is audited. Placeholder: records nothing. The real call must be awaited before data is shown. */
  auditView: (screen: ViewScreen, tenantId?: string) => void;
};

const NOT_WIRED: PortResult = { ok: false, reason: 'not_wired' };

export const placeholderPort: SupportGrantPort = {
  request: async () => NOT_WIRED,
  approve: async () => NOT_WIRED,
  revoke: async () => NOT_WIRED,
  auditView: () => undefined,
};
