import { isStaffRole, type StaffClaims, type StaffRole } from './types';

export type DenyReason = 'no_session' | 'wrong_realm' | 'mfa_required' | 'stale_session' | 'no_role';

export type StaffSessionView =
  | { status: 'denied'; reason: DenyReason }
  | {
      status: 'ready';
      staffId: string;
      roles: ReadonlyArray<StaffRole>;
      mfaSatisfied: true;
      sessionVersion: number;
    };

/**
 * View-model of the staff session. Deny by default, in this order: no claims, not the staff realm,
 * MFA not satisfied (always mandatory for staff), session version older than the current one
 * (revoked), no known staff role. `currentSessionVersion` comes from the identity service once
 * wired. It is required: when it is missing the check cannot run, so the session is stale (fail closed).
 */
export function buildStaffSessionView(
  claims: StaffClaims | null | undefined,
  currentSessionVersion: number | undefined,
): StaffSessionView {
  if (!claims || typeof claims !== 'object') return { status: 'denied', reason: 'no_session' };
  if (claims.realm !== 'staff') return { status: 'denied', reason: 'wrong_realm' };
  if (claims.mfaSatisfied !== true) return { status: 'denied', reason: 'mfa_required' };
  if (
    typeof claims.sessionVersion !== 'number' ||
    typeof currentSessionVersion !== 'number' ||
    claims.sessionVersion !== currentSessionVersion
  )
    return { status: 'denied', reason: 'stale_session' };
  const roles = Array.isArray(claims.roles) ? claims.roles.filter(isStaffRole) : [];
  if (!roles.length || typeof claims.staffId !== 'string' || !claims.staffId)
    return { status: 'denied', reason: 'no_role' };
  return { status: 'ready', staffId: claims.staffId, roles: [...new Set(roles)], mfaSatisfied: true, sessionVersion: claims.sessionVersion };
}
