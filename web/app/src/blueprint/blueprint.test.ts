import { describe, expect, it } from 'vitest';
import { canViewBlueprint, scopeOf } from './access';
import { layoutFlow } from './flows';
import { fixtureBlueprint as bp, fixturePending } from './fixture';
import { classOf, summarisePending } from './pending';
import { buildBlueprintView } from './summary';
import messagesEn from '../../messages/en.json';
import messagesAr from '../../messages/ar.json';
import type { Msg, Section } from './types';

// Built from fragments so this file never spells the engine's name.
const ENGINE = new RegExp(['fra' + 'ppe', 'ERP' + 'Next', 'core\\.', 'compliance\\.zatca_sa'].join('|'), 'i');
const view = (roles: string[], locale = 'en') => buildBlueprintView(bp, { roleIds: roles }, locale, fixturePending);
const ids = (roles: string[]) => view(roles).sections.map((s) => s.id);

describe('access, deny by default', () => {
  it('shows nothing to unknown or empty roles', () => {
    expect(view([]).sections).toEqual([]);
    expect(view(['nobody']).sections).toEqual([]);
    expect(canViewBlueprint(bp, { roleIds: ['nobody'] })).toBe(false);
  });
  it('lets the owner and the general manager see every section', () => {
    for (const r of ['owner', 'general_manager']) {
      expect(view([r]).scope).toBe('all');
      expect(ids([r])).toEqual(['profile', 'places', 'roles', 'flows', 'items', 'numbering', 'settings', 'assistants', 'pending']);
    }
  });
  it('limits other roles to their own department', () => {
    const v = view(['sales_rep']);
    expect(v.scope).toBe('department');
    expect(ids(['sales_rep'])).not.toContain('profile');
    expect(ids(['sales_rep'])).not.toContain('settings');
    expect(ids(['sales_rep'])).not.toContain('pending');
    const roles = v.sections.find((s) => s.id === 'roles');
    expect(roles?.id === 'roles' && roles.roles.map((r) => r.id)).toEqual(['sales_rep']);
    const asst = v.sections.find((s) => s.id === 'assistants');
    expect(asst?.id === 'assistants' && asst.assistants.map((a) => a.id)).toEqual(['sales_assistant']);
    expect(scopeOf(bp, { roleIds: ['warehouse_keeper'] }).locations.has('main_warehouse')).toBe(true);
  });
  it('hides fields a role may not see (fail closed)', () => {
    const items = view(['sales_rep']).sections.find((s) => s.id === 'items');
    const customer = items?.id === 'items' ? items.entities.find((e) => e.id === 'customer') : undefined;
    expect(customer?.fields.map((f) => f.id)).not.toContain('credit_limit');
    expect(customer?.fields.map((f) => f.id)).toContain('customer_name');
  });
  it('does not leak other departments data to the accountant', () => {
    const flows = view(['accountant']).sections.find((s) => s.id === 'flows');
    expect(flows?.id === 'flows' && flows.flows.map((f) => f.entity)).toEqual(['Sales order']);
  });
});

describe('plain-language content', () => {
  it('turns the sales flow into numbered steps with who, rules and approval', () => {
    const s = view(['owner']).sections.find((x) => x.id === 'flows');
    if (s?.id !== 'flows') throw new Error('flows');
    const f = s.flows[0]!;
    expect(f.steps).toHaveLength(5);
    expect(f.steps[1]).toMatchObject({ action: 'Send for approval', from: 'Draft', to: 'Pending approval', who: 'Sales rep and Owner' });
    expect(f.steps[1]!.rules[0]).toMatchObject({ key: 'guard.gte' });
    expect(f.steps[2]!.approval?.key).toBe('flow.approval');
  });
  it('builds numbering samples from code', () => {
    const s = view(['owner']).sections.find((x) => x.id === 'numbering');
    expect(s?.id === 'numbering' && s.rows[0]?.sample).toBe('SO-00001');
  });
  it('marks draft and unverified', () => {
    const v = view(['owner']);
    expect(v.badges.draft).toBe(true);
    const settings = v.sections.find((s) => s.id === 'settings');
    expect(settings?.badges.unverified).toBe(true);
  });
  it('uses the locale for names and keeps keys only for sentences', () => {
    const s = view(['owner'], 'ar').sections.find((x) => x.id === 'flows');
    expect(s?.id === 'flows' && s.flows[0]?.steps[0]?.from).toBe('مسودة');
  });
  it('never names the engine or a component id in the view-model', () => {
    for (const loc of ['en', 'ar']) expect(JSON.stringify(view(['owner'], loc))).not.toMatch(ENGINE);
    expect(JSON.stringify(messagesEn.blueprint) + JSON.stringify(messagesAr.blueprint)).not.toMatch(ENGINE);
  });
  it('only emits message keys that exist in both languages', () => {
    const has = (o: unknown, path: string) => path.split('.').reduce<unknown>((a, k) => (a as Record<string, unknown> | undefined)?.[k], o) !== undefined;
    const keys: string[] = [];
    const walk = (m: Msg) => {
      keys.push(m.key);
      Object.values(m.params ?? {}).forEach((p) => typeof p === 'object' && walk(p));
    };
    const msgs = (s: Section): Msg[] => {
      switch (s.id) {
        case 'profile': return s.facts.flatMap((f) => [f.label, ...(typeof f.value === 'string' ? [] : [f.value])]);
        case 'settings': return s.facts.flatMap((f) => [f.label, ...(typeof f.value === 'string' ? [] : [f.value])]);
        case 'places': return [...s.locations.map((l) => l.kind), ...s.departments.map((d) => d.label)];
        case 'roles': return s.roles.flatMap((r) => [r.scope, ...r.rules.flatMap((p) => p.actions)]);
        case 'flows': return s.flows.flatMap((f) => f.steps.flatMap((x) => [...x.rules, ...(x.approval ? [x.approval] : [])]));
        case 'items': return s.entities.flatMap((e) => e.fields.map((f) => f.type));
        case 'numbering': return s.rows.map((r) => r.reset);
        case 'assistants': return s.assistants.flatMap((a) => [a.department, a.limits, a.memory, ...a.tools.map((t) => t.text)]);
        case 'pending': return s.groups.flatMap((g) => g.items);
      }
    };
    for (const r of ['owner', 'sales_rep']) for (const s of view([r]).sections) msgs(s).forEach(walk);
    for (const k of new Set(keys)) {
      expect(has(messagesEn.blueprint, k), `en ${k}`).toBe(true);
      expect(has(messagesAr.blueprint, k), `ar ${k}`).toBe(true);
    }
  });
});

describe('flow layout', () => {
  it('puts steps in columns by distance from the start', () => {
    const l = layoutFlow(bp.workflows![0]!, (x, id) => x.en ?? id);
    const col = (id: string) => l.nodes.find((n) => n.id === id)!.col;
    expect([col('draft'), col('pending_approval'), col('approved'), col('delivered')]).toEqual([0, 1, 1, 2]);
    expect(col('cancelled')).toBe(1);
    expect(l.edges).toHaveLength(5);
    expect(l.edges.some((e) => e.back)).toBe(false);
  });
  it('flags a step that goes back', () => {
    const wf = { id: 'w', entity: 'x', labels: {}, states: [{ id: 'a', kind: 'initial', labels: {} }, { id: 'b', labels: {} }], transitions: [{ id: 't1', from: 'a', to: 'b', actionLabels: {}, allowedRoles: [] }, { id: 't2', from: 'b', to: 'a', actionLabels: {}, allowedRoles: [] }] };
    expect(layoutFlow(wf, (_l, id) => id).edges.map((e) => e.back)).toEqual([false, true]);
  });
});

describe('pending changes', () => {
  it('folds the diff impact classes into cosmetic, process, access and money', () => {
    expect(fixturePending.map(classOf)).toEqual(['money', 'access', 'process', 'cosmetic']);
    const p = summarisePending(fixturePending, 'en');
    expect(p.total).toBe(4);
    expect(p.groups.map((g) => [g.cls, g.count])).toEqual([['money', 1], ['access', 1], ['process', 1], ['cosmetic', 1]]);
  });
  it('is empty without changes', () => {
    expect(summarisePending([], 'en')).toEqual({ total: 0, groups: [] });
  });
});
