import { describe, expect, it } from 'vitest';
import { buildNav } from './navigation';
import { callerOf, fixtureSession, placeholderSwitchWorkspace } from './session';
import { fixtureData } from '../records/fixture/rows';

const ids = (roles: string[], locale = 'en') =>
  buildNav(fixtureData, { roleIds: roles }, locale, { home: 'Home' }).flatMap((s) => s.items.map((i) => i.id));

describe('buildNav', () => {
  it('always offers home and lists only entities the roles may list', () => {
    expect(ids(['owner'])).toContain('home');
    expect(ids(['owner'])).toContain('sales_order');
    expect(ids(['nobody'])).toEqual(['home']); // deny by default
    expect(ids([])).toEqual(['home']);
  });
  it('labels in the locale and links to the record routes', () => {
    const nav = buildNav(fixtureData, { roleIds: ['owner'] }, 'ar', { home: 'x' });
    const so = nav.flatMap((s) => s.items).find((i) => i.id === 'sales_order');
    expect(so?.href).toBe('/records/sales_order/');
    expect(so?.label).toBe('أوامر البيع');
  });
});

describe('session placeholder', () => {
  it('mirrors one tenant token and refuses a suspended workspace', async () => {
    if (fixtureSession.status !== 'ready') throw new Error('fixture');
    const ok = await placeholderSwitchWorkspace(fixtureSession.claims, 'tenant-fixture-b');
    expect(ok.ok && ok.claims.tenantId).toBe('tenant-fixture-b');
    expect(callerOf(fixtureSession.claims).roleIds).toEqual(['owner']);
    expect((await placeholderSwitchWorkspace(fixtureSession.claims, 'tenant-fixture-c')).ok).toBe(false);
    expect((await placeholderSwitchWorkspace(fixtureSession.claims, 'unknown')).ok).toBe(false);
  });
});
