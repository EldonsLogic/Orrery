import { can } from './access';
import {
  MAX_PENDING,
  MAX_REASON_LEN,
  MAX_SUPPORT_SECONDS,
  PENDING_TTL,
  type GrantRecord,
  type TenantMeta,
} from './types';

export type GrantState = 'pending' | 'approved' | 'revoked' | 'expired' | 'lapsed';

/** `lapsed` is a request nobody approved in time; `expired` is an approved grant whose time ran out. */
export function grantState(g: GrantRecord, now: number): GrantState {
  if (g.status === 'revoked') return 'revoked';
  if (g.status === 'pending') return g.requestedAt + PENDING_TTL > now ? 'pending' : 'lapsed';
  return g.expiresAt !== undefined && g.expiresAt > now ? 'approved' : 'expired';
}

export const remainingSeconds = (g: GrantRecord, now: number): number =>
  grantState(g, now) === 'approved' ? Math.max(0, (g.expiresAt as number) - now) : 0;

/** HH:MM:SS, digits stay left to right. */
export function formatClock(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  const p = (n: number) => String(n).padStart(2, '0');
  return `${p(Math.floor(s / 3600))}:${p(Math.floor((s % 3600) / 60))}:${p(s % 60)}`;
}

export function formatUtc(at: number): string {
  return `${new Date(at * 1000).toISOString().slice(0, 16).replace('T', ' ')} UTC`;
}

export type GrantRow = { grant: GrantRecord; state: GrantState; remaining: number };
export type GrantsScreen = { pending: GrantRow[]; approved: GrantRow[]; closed: GrantRow[] };

/**
 * Group grants for the screen. `support` sees only its own. There are no approve or revoke actions:
 * only a customer-realm tenant owner or admin with step-up can do either (identity, ADR-0007 point 7),
 * so a pending row just reads "Awaiting tenant approval".
 */
export function buildGrantsScreen(
  grants: ReadonlyArray<GrantRecord>,
  roles: ReadonlyArray<unknown>,
  staffId: string,
  now: number,
): GrantsScreen {
  const all = can(roles, 'grants.view.all');
  const own = can(roles, 'grants.view.own');
  const rows = grants
    .filter((g) => all || (own && g.staffId === staffId))
    .map((grant): GrantRow => {
      const state = grantState(grant, now);
      return { grant, state, remaining: remainingSeconds(grant, now) };
    })
    .sort((a, b) => b.grant.requestedAt - a.grant.requestedAt);
  return {
    pending: rows.filter((r) => r.state === 'pending'),
    approved: rows.filter((r) => r.state === 'approved'),
    closed: rows.filter((r) => r.state === 'revoked' || r.state === 'expired' || r.state === 'lapsed'),
  };
}

export type RequestDraft = { tenantId: string; reason: string; scope: ReadonlyArray<string>; durationMinutes: number };
export type RequestError = 'forbidden' | 'tenant' | 'reason' | 'scope' | 'duration' | 'cap';

/** Mirrors identity request(): open tenant, 1..500 char reason, non-empty scope, 1..240 minutes, five pending at most. */
export function validateRequest(
  draft: RequestDraft,
  roles: ReadonlyArray<unknown>,
  staffId: string,
  tenants: ReadonlyArray<TenantMeta>,
  grants: ReadonlyArray<GrantRecord>,
  now: number,
): RequestError[] {
  if (!can(roles, 'grants.request')) return ['forbidden'];
  const errors: RequestError[] = [];
  const t = tenants.find((x) => x.tenantId === draft.tenantId);
  if (!t || (t.status !== 'active' && t.status !== 'trial')) errors.push('tenant');
  const reason = draft.reason.trim();
  if (!reason || reason.length > MAX_REASON_LEN) errors.push('reason');
  if (!draft.scope.length) errors.push('scope');
  const secs = draft.durationMinutes * 60;
  if (!Number.isInteger(draft.durationMinutes) || secs <= 0 || secs > MAX_SUPPORT_SECONDS) errors.push('duration');
  const pending = grants.filter((g) => g.staffId === staffId && g.tenantId === draft.tenantId && grantState(g, now) === 'pending');
  if (pending.length >= MAX_PENDING) errors.push('cap');
  return errors;
}

/** Scope items staff may ask for. Metadata-level names, defined with PLT-019 and SEC-008. */
export const SCOPE_OPTIONS = ['diagnostics', 'configuration', 'audit_log', 'records_read'] as const;

/** The live approved grant that lets this staff member into this tenant, if any. */
export function liveGrantFor(grants: ReadonlyArray<GrantRecord>, staffId: string, tenantId: string, now: number): GrantRecord | null {
  return grants.find((g) => g.staffId === staffId && g.tenantId === tenantId && grantState(g, now) === 'approved') ?? null;
}
