import { isStaffRole, type StaffRole } from './types';

/** What a screen or action needs. Deny by default: a permission nobody lists is nobody's. */
export type Permission =
  | 'tenants.view'
  | 'grants.view.own'
  | 'grants.view.all'
  | 'grants.request'
  | 'audit.view.own'
  | 'audit.view.all'
  | 'factory.view'
  | 'factory.review';

/**
 * UI-ONLY PROPOSAL, not an authorization design. Identity has no staff role claim yet (Q-225 b), so
 * these four roles and this table need an ADR and a security review before the console is accepted.
 * Staff cannot approve or revoke a grant: identity allows that only for a customer-realm tenant
 * owner or admin with step-up (ADR-0007 point 7), so no staff role here carries those permissions.
 * Factory review (PLT-014): the server's reviewer roles are `component_reviewer` and `platform_admin` (BPL-016);
 * which staff role maps to them is open (Q-470). These two permissions only decide what the screen offers.
 */
const TABLE: Readonly<Record<StaffRole, ReadonlyArray<Permission>>> = {
  support: ['tenants.view', 'grants.view.own', 'grants.request', 'audit.view.own'],
  tenant_admin_staff: ['tenants.view', 'grants.view.all', 'grants.request', 'audit.view.all', 'factory.view'],
  security: ['tenants.view', 'grants.view.all', 'audit.view.all', 'factory.view', 'factory.review'],
  owner: [
    'tenants.view',
    'grants.view.all',
    'grants.request',
    'audit.view.all',
    'factory.view',
    'factory.review',
  ],
};

/** True only if some KNOWN role grants it. Unknown roles, empty lists and non-arrays deny. */
export function can(roles: ReadonlyArray<unknown> | null | undefined, permission: Permission): boolean {
  if (!Array.isArray(roles)) return false;
  return roles.some((r) => isStaffRole(r) && TABLE[r].includes(permission));
}

export const canSeeGrants = (roles: ReadonlyArray<unknown>) => can(roles, 'grants.view.all') || can(roles, 'grants.view.own');
export const canSeeAudit = (roles: ReadonlyArray<unknown>) => can(roles, 'audit.view.all') || can(roles, 'audit.view.own');
