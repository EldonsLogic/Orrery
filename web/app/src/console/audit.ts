import { can } from './access';
import type { AuditEntry } from './types';

export type AuditFilter = { tenant?: string; actor?: string; action?: string };

/**
 * Newest first. `audit.view.all` sees everything; `audit.view.own` only entries whose subject is the
 * viewer; no permission sees nothing. Filters are exact matches (an empty filter matches all).
 */
export function buildAuditView(
  entries: ReadonlyArray<AuditEntry>,
  roles: ReadonlyArray<unknown>,
  staffId: string,
  filter: AuditFilter = {},
): AuditEntry[] {
  const all = can(roles, 'audit.view.all');
  if (!all && !can(roles, 'audit.view.own')) return [];
  return entries
    .filter((e) => all || e.subject === staffId)
    .filter((e) => !filter.tenant || e.tenant === filter.tenant)
    .filter((e) => !filter.actor || e.subject === filter.actor)
    .filter((e) => !filter.action || e.action === filter.action)
    .slice()
    .sort((a, b) => b.at - a.at || b.seq - a.seq);
}

export const distinct = (vals: ReadonlyArray<string | null>): string[] =>
  [...new Set(vals.filter((v): v is string => !!v))].sort();
