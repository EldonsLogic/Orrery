// Deny by default. The contract (contracts/blueprint.schema.json, role.isAdmin) says only roles with isAdmin may change
// branding, so the caller needs a role of the active tenant's Blueprint with isAdmin === true. A function name such as
// owner or general manager grants nothing by itself, and a delegated admin with any other role is allowed.
// TODO(partner lane, gateway): the gateway must enforce the same rule on save and re-run the colour derivation;
// this check only hides what would be refused and is never the control.
import type { Blueprint, Caller } from '../../blueprint/types';

export const canEditBranding = (bp: Blueprint, caller: Caller): boolean =>
  bp.roles.some((r) => r.isAdmin === true && caller.roleIds.includes(r.id));
