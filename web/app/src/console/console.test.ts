import { describe, expect, it } from 'vitest';
import { can } from './access';
import { buildAuditView } from './audit';
import { buildGrantBanner } from './banner';
import { fixtureData, FIXTURE_NOW as NOW } from './fixture';
import { buildGrantsScreen, formatClock, grantState, validateRequest } from './grants';
import { placeholderPort } from './port';
import { buildStaffSessionView } from './staffSession';
import { buildTenantList } from './tenants';
import type { StaffClaims, TenantMeta } from './types';

const claims = (over: Partial<StaffClaims> = {}): StaffClaims => ({ realm: 'staff', staffId: 's1', roles: ['support'], mfaSatisfied: true, sessionVersion: 1, ...over });
const data = fixtureData(NOW);

describe('staff session view', () => {
  it('is ready only for a staff realm token with MFA, a live version and a known role', () => {
    expect(buildStaffSessionView(claims()).status).toBe('ready');
    expect(buildStaffSessionView(null)).toEqual({ status: 'denied', reason: 'no_session' });
    expect(buildStaffSessionView(claims({ realm: 'customer' }))).toEqual({ status: 'denied', reason: 'wrong_realm' });
    expect(buildStaffSessionView(claims({ mfaSatisfied: false }))).toEqual({ status: 'denied', reason: 'mfa_required' });
    expect(buildStaffSessionView(claims(), 2)).toEqual({ status: 'denied', reason: 'stale_session' });
    expect(buildStaffSessionView(claims({ roles: ['admin', 'sales_rep'] }))).toEqual({ status: 'denied', reason: 'no_role' });
    expect(buildStaffSessionView(claims({ roles: 'support' as never }))).toEqual({ status: 'denied', reason: 'no_role' });
  });
});

describe('role checks deny by default', () => {
  it('denies unknown roles, empty and malformed lists', () => {
    for (const r of [[], ['root'], null, undefined, 'owner']) expect(can(r as never, 'tenants.view')).toBe(false);
    expect(can(['support'], 'grants.approve')).toBe(false);
    expect(can(['support'], 'audit.view.all')).toBe(false);
    expect(can(['security'], 'grants.request')).toBe(false);
    expect(can(['security'], 'grants.revoke')).toBe(true);
    expect(can(['support', 'security'], 'grants.revoke')).toBe(true);
  });
});

describe('tenant list', () => {
  it('returns metadata only, even if a source row carries more', () => {
    const rich = [{ ...data.tenants[0], contactEmail: 'x@example.test', revenue: 9 }] as unknown as TenantMeta[];
    const [row] = buildTenantList(rich, ['support']);
    expect(Object.keys(row).sort()).toEqual(['health', 'name', 'plan', 'region', 'status', 'tenantId']);
  });
  it('searches name and id and filters; no permission shows nothing', () => {
    expect(buildTenantList(data.tenants, ['support'], { query: 'foods' }).map((r) => r.tenantId)).toEqual(['tenant-fixture-b']);
    expect(buildTenantList(data.tenants, ['support'], { query: 'fixture-d' })).toHaveLength(1);
    expect(buildTenantList(data.tenants, ['support'], { region: 'sa', status: 'active' })).toHaveLength(1);
    expect(buildTenantList(data.tenants, [])).toEqual([]);
  });
});

describe('grants', () => {
  it('derives states and the countdown', () => {
    const [approved, pending, revoked] = data.grants;
    expect(grantState(approved, NOW)).toBe('approved');
    expect(grantState(approved, NOW + 2100)).toBe('expired');
    expect(grantState(pending, NOW)).toBe('pending');
    expect(grantState(pending, NOW + 24 * 3600)).toBe('lapsed');
    expect(grantState(revoked, NOW)).toBe('revoked');
    expect(formatClock(3725)).toBe('01:02:05');
  });
  it('groups and offers actions by role; nobody approves their own request', () => {
    const owner = buildGrantsScreen(data.grants, ['owner'], 's-other', NOW);
    expect(owner.pending[0].actions).toEqual(['approve', 'revoke']);
    expect(owner.approved).toHaveLength(1);
    expect(owner.closed).toHaveLength(1);
    expect(buildGrantsScreen(data.grants, ['owner'], 'staff-fixture-2', NOW).pending[0].actions).toEqual(['revoke']);
    const support = buildGrantsScreen(data.grants, ['support'], 'staff-fixture-1', NOW);
    expect(support.pending).toEqual([]);
    expect(support.approved[0].actions).toEqual([]);
    expect(buildGrantsScreen(data.grants, [], 'staff-fixture-1', NOW)).toEqual({ pending: [], approved: [], closed: [] });
  });
  it('validates a request like identity does', () => {
    const ok = { tenantId: 'tenant-fixture-a', reason: 'why', scope: ['diagnostics'], durationMinutes: 60 };
    const v = (d = ok, roles: string[] = ['support']) => validateRequest(d, roles, 's1', data.tenants, data.grants, NOW);
    expect(v()).toEqual([]);
    expect(v(ok, ['security'])).toEqual(['forbidden']);
    expect(v({ ...ok, tenantId: 'tenant-fixture-c' })).toEqual(['tenant']);
    expect(v({ ...ok, reason: '  ' })).toEqual(['reason']);
    expect(v({ ...ok, scope: [] })).toEqual(['scope']);
    expect(v({ ...ok, durationMinutes: 241 })).toEqual(['duration']);
    expect(v({ ...ok, durationMinutes: 1.5 })).toEqual(['duration']);
  });
  it('the placeholder port never executes anything', async () => {
    const draft = { tenantId: 'tenant-fixture-a', reason: 'r', scope: ['diagnostics'], durationMinutes: 5 };
    for (const r of [await placeholderPort.request(draft), await placeholderPort.approve('g'), await placeholderPort.revoke('g')])
      expect(r).toEqual({ ok: false, reason: 'not_wired' });
  });
});

describe('audit view', () => {
  it('filters by tenant, actor and action, newest first, and limits support to its own', () => {
    const all = buildAuditView(data.audit, ['security'], 'x');
    expect(all[0].seq).toBe(6 + 1);
    expect(buildAuditView(data.audit, ['security'], 'x', { tenant: 'tenant-fixture-d' })).toHaveLength(3);
    expect(buildAuditView(data.audit, ['security'], 'x', { actor: 'staff-fixture-2' })).toHaveLength(1);
    expect(buildAuditView(data.audit, ['security'], 'x', { action: 'support.access' })).toHaveLength(1);
    expect(buildAuditView(data.audit, ['support'], 'staff-fixture-2').every((e) => e.subject === 'staff-fixture-2')).toBe(true);
    expect(buildAuditView(data.audit, [], 'staff-fixture-1')).toEqual([]);
  });
});

describe('grant banner', () => {
  it('shows with time left only inside a tenant under a live grant', () => {
    const b = buildGrantBanner(data.grants, data.tenants, 'staff-fixture-1', 'tenant-fixture-a', NOW);
    expect(b).toMatchObject({ tenantName: 'Sample Trading Co', remaining: 2100, low: false });
    expect(buildGrantBanner(data.grants, data.tenants, 'staff-fixture-1', 'tenant-fixture-a', NOW + 1600)?.low).toBe(true);
    expect(buildGrantBanner(data.grants, data.tenants, 'staff-fixture-1', 'tenant-fixture-a', NOW + 2100)).toBeNull();
    expect(buildGrantBanner(data.grants, data.tenants, 'staff-fixture-1', null, NOW)).toBeNull();
    expect(buildGrantBanner(data.grants, data.tenants, 'staff-fixture-1', 'tenant-fixture-b', NOW)).toBeNull();
    expect(buildGrantBanner(data.grants, data.tenants, 'staff-fixture-2', 'tenant-fixture-a', NOW)).toBeNull();
  });
});
