/**
 * Tenant from the host (ADR-0007: the tenant comes from the address host only, never a query string,
 * body or header). The mapping is local and synthetic until the gateway resolves hosts (PLT); the
 * gateway will validate the tenant again server-side, this is only the look of the page.
 */
export const SYNTHETIC_HOSTS: Readonly<Record<string, string>> = {
  'sample-trading.localhost': 'sample-trading',
  'example-foods.localhost': 'example-foods',
};

export function tenantFromHost(hostname: string | null | undefined, map: Readonly<Record<string, string>> = SYNTHETIC_HOSTS): string | null {
  if (typeof hostname !== 'string') return null;
  const h = hostname.trim().toLowerCase().replace(/\.$/, '');
  return Object.prototype.hasOwnProperty.call(map, h) ? map[h]! : null;
}

/** Only `hostname` is read: any `search` or `hash` on the location is ignored on purpose. */
export function tenantFromLocation(loc: { hostname: string }, map?: Readonly<Record<string, string>>): string | null {
  return tenantFromHost(loc.hostname, map);
}
