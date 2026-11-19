import type { RequestDraft } from './grants';

/**
 * PLACEHOLDER port to the identity service (support.request only). REAL WIRING GOES HERE (PLT-019,
 * with SEC-008): call identity with the staff token. Staff cannot approve or revoke: identity takes
 * those only from a customer-realm tenant owner or admin with a fresh MFA step-up (ADR-0007 point 7),
 * so the port has no such calls. This placeholder NEVER executes anything: it has a fixed result,
 * stores nothing and logs nothing. Open question Q-225.
 */
export type PortResult = { ok: false; reason: 'not_wired' };
export type ViewScreen = 'tenants' | 'grants' | 'audit' | 'tenant_banner';

export type SupportGrantPort = {
  request: (draft: RequestDraft) => Promise<PortResult>;
  /**
   * Every console view is audited, and the audit must resolve BEFORE any tenant data is shown:
   * callers show nothing until it resolves and show nothing if it rejects (see guard.ts).
   * Placeholder: records nothing and resolves at once.
   */
  auditView: (screen: ViewScreen, tenantId?: string) => Promise<void>;
};

const NOT_WIRED: PortResult = { ok: false, reason: 'not_wired' };

export const placeholderPort: SupportGrantPort = {
  request: async () => NOT_WIRED,
  auditView: async () => undefined,
};
