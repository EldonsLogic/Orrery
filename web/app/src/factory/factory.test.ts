// PLT-014: pure rules of the factory review screens (text safety, action availability).
import { describe, expect, it } from 'vitest';
import { actionState, countByStatus, evidencedTenants, filterByStatus } from './model';
import { fixtureRequests } from './fixture';
import { plainText, detailLines } from './text';
import { REQUEST_STATUSES, type ComponentRequestRecord } from './types';

const byId = (id: string) => fixtureRequests.find((r) => r.id === id) as ComponentRequestRecord;
const owner = { staffId: 'staff-owner-x', roles: ['owner'] as const };
const READY = byId('CR-0a1b2c3d4e5f6071');

describe('plainText', () => {
  it('replaces bidi and control characters with a visible marker', () => {
    const out = plainText('a\u202eb\u0000c\u200fd\u2066e\ufeff');
    expect(out).toBe('a<U+202E>b<U+0000>c<U+200F>d<U+2066>e<U+FEFF>');
    expect(out).not.toMatch(/[\u202a-\u202e\u2066\u200f\ufeff]/);
  });
  it('keeps markup as text and Arabic untouched, cuts long text, tolerates odd values', () => {
    expect(plainText('<script>alert(1)</script>')).toBe('<script>alert(1)</script>');
    expect(plainText('سجل الزيارات')).toBe('سجل الزيارات');
    expect(plainText('x'.repeat(5000)).length).toBe(2001);
    expect(plainText(null)).toBe('');
    expect(plainText({ a: '\u202e' })).toContain('<U+202E>');
    const cyc: Record<string, unknown> = {};
    cyc.self = cyc;
    expect(plainText(cyc)).toBe('');
  });
  it('turns event detail into text lines', () => {
    expect(detailLines({ why: 'x\u202e', n: 2 })).toEqual(['why: x<U+202E>', 'n: 2']);
    expect(detailLines(null)).toEqual([]);
    expect(detailLines([1])).toEqual([]);
  });
});

describe('actionState', () => {
  it('is on for an unrelated reviewer with permission, right status and evidence', () => {
    expect(actionState(READY, owner, 'approve', 2)).toEqual({ enabled: true });
    expect(actionState(READY, owner, 'reject', 2)).toEqual({ enabled: true });
    expect(actionState(READY, owner, 'attest_generalisable', 2)).toEqual({ enabled: true });
  });
  it('is off with no permission, for unknown roles and for a missing staff id (deny by default)', () => {
    expect(actionState(READY, { staffId: 'x', roles: ['support'] }, 'approve', 2)).toEqual({ enabled: false, reason: 'no_permission' });
    expect(actionState(READY, { staffId: 'x', roles: [] }, 'approve', 2)).toEqual({ enabled: false, reason: 'no_permission' });
    expect(actionState(READY, { staffId: '', roles: ['owner'] }, 'approve', 2)).toEqual({ enabled: false, reason: 'separation' });
  });
  it('is off in the wrong status', () => {
    expect(actionState(byId('CR-718293041526a7b8'), owner, 'approve', 2)).toEqual({ enabled: false, reason: 'wrong_status' });
    expect(actionState(READY, owner, 'attest_risk_class', 2)).toEqual({ enabled: false, reason: 'wrong_status' });
  });
  it('shows separation of duties, case-insensitively, for requester, drafter, submitter and attester', () => {
    for (const who of ['AGENT-DISCOVERY', 'agent-drafter']) expect(actionState(READY, { staffId: who, roles: ['owner'] }, 'reject', 2)).toEqual({ enabled: false, reason: 'separation' });
    const attested = byId('CR-4e5f607182930415');
    expect(actionState(attested, { staffId: 'Staff-Fixture-1', roles: ['owner'] }, 'approve', 2)).toEqual({ enabled: false, reason: 'separation' });
    // an earlier attester may still reject (server rule: only approval bars attesters)
    expect(actionState(attested, { staffId: 'staff-fixture-1', roles: ['owner'] }, 'reject', 2)).toEqual({ enabled: true });
  });
  it('never offers plain for a draft with a money field, but offers another class', () => {
    const parked = byId('CR-2c3d4e5f60718293');
    expect(actionState(parked, owner, 'attest_risk_class', 2, 'plain')).toEqual({ enabled: false, reason: 'money_field' });
    expect(actionState(parked, owner, 'attest_risk_class', 2, 'ledger')).toEqual({ enabled: true });
  });
  it('needs a draft attestation or a proven draft, and general evidence, to approve', () => {
    const one = byId('CR-1b2c3d4e5f607182');
    expect(evidencedTenants(one)).toBe(1);
    expect(actionState(one, owner, 'approve', 2)).toEqual({ enabled: false, reason: 'no_generalisation' });
    expect(actionState({ ...one, generalisation: { attested_by: 'someone', attested_at: 'x' } }, owner, 'approve', 2)).toEqual({ enabled: true });
    const unproven = { ...READY, classification: { ...READY.classification, draft: { proven: false, reasons: ['field_type'], has_money_field: false } } };
    expect(actionState(unproven, owner, 'approve', 2)).toEqual({ enabled: false, reason: 'needs_attestation' });
    const stale = { ...unproven, classification: { ...unproven.classification, draft_attested_digest: 'old' } };
    expect(actionState(stale, owner, 'approve', 2)).toEqual({ enabled: false, reason: 'needs_attestation' });
    const good = { ...unproven, classification: { ...unproven.classification, draft_attested_digest: READY.draft_digest, draft_attested_by: 'other' } };
    expect(actionState(good, owner, 'approve', 2)).toEqual({ enabled: true });
  });
  it('does not count a tenant without evidence', () => {
    expect(evidencedTenants({ ...READY, tenants: { a: [], b: [{ kind: 'blueprint', id: '/x/1' }] } })).toBe(1);
  });
});

describe('list helpers', () => {
  it('counts and filters by status', () => {
    const c = countByStatus(fixtureRequests);
    expect(REQUEST_STATUSES.every((s) => c[s] >= 1)).toBe(true);
    expect(filterByStatus(fixtureRequests, 'in_review').every((r) => r.status === 'in_review')).toBe(true);
    expect(filterByStatus(fixtureRequests, '')).toHaveLength(fixtureRequests.length);
  });
});
