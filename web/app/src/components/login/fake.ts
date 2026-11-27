import fixture from './fixture.json';
import type { TenantBranding, TenantBrandingPort } from './branding';

/**
 * FAKE until the tenant token endpoint exists (PLT, theming.md "/tenant/tokens.css"). Returns
 * synthetic tenants from fixture.json (values produced by derive_tenant_theme.py); unknown keys
 * resolve to null so the page shows the platform look. No network, no credential.
 */
export const fakeBrandingPort: TenantBrandingPort = {
  async load(tenantKey) {
    const all = fixture.tenants as Record<string, unknown>;
    return Object.prototype.hasOwnProperty.call(all, tenantKey) ? (all[tenantKey] as TenantBranding) : null;
  },
};
