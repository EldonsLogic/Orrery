// Deny by default. Document templates are tenant branding, so the same rule as Settings > Branding applies:
// the caller needs a role of the active tenant's Blueprint with isAdmin === true (contracts/blueprint.schema.json).
// TODO(partner lane, gateway): the gateway must enforce this on save; this check only hides what would be refused.
import { canEditBranding } from '../branding/access';

export const canEditDocumentTemplates = canEditBranding;
