import { isStaffRole, type StaffRole } from './types';

/** What a screen or action needs. Deny by default: a permission nobody lists is nobody's. */
export type Permission =
  | 'tenants.view'
  | 'grants.view.own'
  | 'grants.view.all'
  | 'grants.request'
  | 'grants.approve'
  | 'grants.revoke'
  | 'audit.view.own'
  | 'audit.view.all';

const TABLE: Readonly<Record<StaffRole, ReadonlyArray<Permission>>> = {
  support: ['tenants.view', 'grants.view.own', 'grants.request', 'audit.view.own'],
  tenant_admin_staff: ['tenants.view', 'grants.view.all', 'grants.request', 'audit.view.all'],
  security: ['tenants.view', 'grants.view.all', 'grants.approve', 'grants.revoke', 'audit.view.all'],
  owner: [
    'tenants.view',
    'grants.view.all',
    'grants.request',
    'grants.approve',
    'grants.revoke',
    'audit.view.all',
  ],
};

/** True only if some KNOWN role grants it. Unknown roles, empty lists and non-arrays deny. */
export function can(roles: ReadonlyArray<unknown> | null | undefined, permission: Permission): boolean {
  if (!Array.isArray(roles)) return false;
  return roles.some((r) => isStaffRole(r) && TABLE[r].includes(permission));
}

export const canSeeGrants = (roles: ReadonlyArray<unknown>) => can(roles, 'grants.view.all') || can(roles, 'grants.view.own');
export const canSeeAudit = (roles: ReadonlyArray<unknown>) => can(roles, 'audit.view.all') || can(roles, 'audit.view.own');
