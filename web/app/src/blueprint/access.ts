// Deny by default: only roles the Blueprint defines count. Owner and general manager see everything;
// every other role sees its own department: its roles, the records it may touch, its assistants.
import type { Blueprint, BpRole, Caller } from './types';

const SEE_ALL = new Set(['owner', 'general_manager']);

export type Scope = {
  all: boolean;
  roles: ReadonlyArray<BpRole>;
  entities: ReadonlySet<string>;
  locations: ReadonlySet<string>;
};

export function scopeOf(bp: Blueprint, caller: Caller): Scope {
  const roles = bp.roles.filter((r) => caller.roleIds.includes(r.id));
  const all = roles.some((r) => SEE_ALL.has(r.function));
  const entities = new Set(roles.flatMap((r) => (r.permissions ?? []).map((p) => p.entity)));
  const locations = new Set(roles.flatMap((r) => (['branch', 'warehouse', 'department'].includes(r.scope.type) ? (r.scope.values ?? []) : [])));
  return { all, roles, entities, locations };
}

/** Nothing opens for a caller with no role the Blueprint knows. */
export const canViewBlueprint = (bp: Blueprint, caller: Caller): boolean => scopeOf(bp, caller).roles.length > 0;
