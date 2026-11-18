import { afterEach, describe, expect, it, vi } from 'vitest';
import { fixtureData } from './fixture/rows';
import { buildActions, executable, modeFor, summarizeChanges } from './actions';
import { buildFormModel } from './formModel';
import { buildListModel, defaultQuery } from './listModel';
import { submitAction } from './submitAction';
import type { Caller, RecordsData, ToolDef } from './types';

const D = fixtureData;
const rep: Caller = { roleIds: ['sales_rep'] };
const owner: Caller = { roleIds: ['owner'] };
const accountant: Caller = { roleIds: ['accountant'] };
const keeper: Caller = { roleIds: ['warehouse_keeper'] };
const without = (name: string): RecordsData => ({ ...D, tools: D.tools.filter((t) => t.name !== name) });
const patch = (name: string, f: (t: ToolDef) => ToolDef): RecordsData => ({ ...D, tools: D.tools.map((t) => (t.name === name ? f(t) : t)) });
const ids = (m: { columns: ReadonlyArray<{ id: string }> }) => m.columns.map((c) => c.id);

describe('list model', () => {
  it('builds columns, status and rows for the fixture entities', () => {
    const m = buildListModel(D, 'sales_order', rep, 'en')!;
    expect(m.title).toBe('Sales orders');
    expect(ids(m)).toEqual(['customer', 'order_date', 'subtotal', 'vat_amount', 'total_amount', 'state']);
    expect(m.columns.find((c) => c.id === 'total_amount')).toMatchObject({ kind: 'money', numeric: true });
    expect(m.columns.find((c) => c.id === 'state')!.filter!.options.map((o) => o.value)).toContain('pending_approval');
    expect(m.total).toBe(6);
    expect(m.rows).toHaveLength(5); // page size 5
    expect(buildListModel(D, 'item', rep, 'ar')!.title).toBe('الأصناف');
    expect(buildListModel(D, 'customer', owner, 'en')).not.toBeNull();
  });
  it('drops hidden columns and cannot be probed through search or filters', () => {
    expect(ids(buildListModel(D, 'customer', rep, 'en')!)).not.toContain('credit_limit');
    expect(ids(buildListModel(D, 'customer', owner, 'en')!)).toContain('credit_limit');
    const q = { ...defaultQuery, search: '50000.00' };
    expect(buildListModel(D, 'customer', rep, 'en', q)!.total).toBe(0);
    expect(buildListModel(D, 'customer', owner, 'en', q)!.total).toBe(1);
    const f = buildListModel(D, 'customer', rep, 'en', { ...defaultQuery, filters: { credit_limit: '50000.00' } })!;
    expect(f.total).toBe(3); // unknown column ignored
    expect(JSON.stringify(f.rows)).not.toContain('50000.00');
  });
  it('searches, filters, sorts and paginates', () => {
    expect(buildListModel(D, 'customer', owner, 'en', { ...defaultQuery, search: 'demo' })!.rows.map((r) => r.id)).toEqual(['CUST-003']);
    const draft = buildListModel(D, 'sales_order', owner, 'en', { ...defaultQuery, filters: { state: 'draft' } })!;
    expect(draft.rows.map((r) => r.id)).toEqual(['SO-00001', 'SO-00006']);
    const sorted = buildListModel(D, 'sales_order', owner, 'en', { ...defaultQuery, sort: { field: 'total_amount', direction: 'desc' }, pageSize: 2 })!;
    expect(sorted.rows.map((r) => r.id)).toEqual(['SO-00002', 'SO-00001']);
    expect(sorted.pageCount).toBe(3);
    const p3 = buildListModel(D, 'sales_order', owner, 'en', { ...defaultQuery, pageSize: 2, page: 99 })!;
    expect(p3.page).toBe(3);
  });
  it('turns links into linked-record cells only where the caller may open the target', () => {
    const cell = (m: NonNullable<ReturnType<typeof buildListModel>>) => m.rows[0]!.cells.find((c) => c.columnId === 'customer')!;
    expect(cell(buildListModel(D, 'sales_order', rep, 'en')!)).toMatchObject({ text: 'Sample Trading Co', href: '/records/customer/CUST-001/' });
    // the warehouse keeper has no customer tools: the id only, no name, no link
    expect(cell(buildListModel(D, 'sales_order', keeper, 'en')!)).toEqual({ columnId: 'customer', kind: 'link', text: 'CUST-001', href: undefined });
  });
  it('colours statuses by meaning', () => {
    const tones = Object.fromEntries(buildListModel(D, 'sales_order', owner, 'en', { ...defaultQuery, pageSize: 10 })!.rows.map((r) => [r.id, r.cells.at(-1)!.tone]));
    expect(tones).toMatchObject({ 'SO-00001': 'neutral', 'SO-00002': 'warning', 'SO-00004': 'success', 'SO-00005': 'danger' });
  });
  it('is denied by default when the list tool is missing or not allowed', () => {
    expect(buildListModel(without('sales_order.list'), 'sales_order', owner, 'en')).toBeNull();
    expect(buildListModel(D, 'sales_invoice', rep, 'en')).toBeNull(); // role not in requires.roles
    expect(buildListModel(D, 'unknown', owner, 'en')).toBeNull();
    expect(buildListModel(D, 'customer', { roleIds: [] }, 'en')).toBeNull();
  });
  it('offers create only with a usable create tool', () => {
    expect(buildListModel(D, 'item', owner, 'en')!.createAction?.tool).toBe('item.create');
    expect(buildListModel(D, 'item', rep, 'en')!.createAction).toBeUndefined();
  });
});

describe('form model', () => {
  it('hides fields by field_access for the caller role', () => {
    const f = buildFormModel(D, 'customer', rep, 'en', 'CUST-001')!;
    expect(f.fields.map((x) => x.id)).toEqual(['customer_name', 'vat_number', 'phone']);
    expect(buildFormModel(D, 'customer', owner, 'en', 'CUST-001')!.fields.map((x) => x.id)).toContain('credit_limit');
    expect(JSON.stringify(f)).not.toContain('50000.00');
  });
  it('marks read-only fields from field_access, computed fields and locked statuses', () => {
    const data = patch('customer.update', (t) => ({ ...t, field_access: { hidden_by_role: {}, read_only_by_role: { sales_rep: ['vat_number'] } } }));
    const c = buildFormModel(data, 'customer', rep, 'en', 'CUST-001')!;
    expect(c.mode).toBe('edit');
    expect(c.fields.find((x) => x.id === 'vat_number')!.readOnly).toBe(true);
    expect(c.fields.find((x) => x.id === 'customer_name')!.readOnly).toBe(false);
    const draft = buildFormModel(D, 'sales_order', rep, 'en', 'SO-00001')!;
    expect(draft.fields.find((x) => x.id === 'total_amount')).toMatchObject({ readOnly: true, control: 'numeric', suffix: 'SAR', value: '1150.00' });
    const locked = buildFormModel(D, 'sales_order', rep, 'en', 'SO-00002')!;
    expect(locked.mode).toBe('view');
    expect(locked.saveAction).toBeUndefined();
    expect(locked.fields.every((x) => x.readOnly)).toBe(true);
  });
  it('omits computed fields on create and keeps required and types', () => {
    const f = buildFormModel(D, 'sales_order', rep, 'en')!;
    expect(f.mode).toBe('create');
    expect(f.fields.map((x) => x.id)).toEqual(['customer', 'order_date']);
    expect(f.fields[0]).toMatchObject({ control: 'link', required: true });
    expect(f.fields[0]!.options![0]!.label).toBe('CUST-001 - Sample Trading Co');
    expect(f.fields[1]).toMatchObject({ control: 'date', inputType: 'date' });
    const item = buildFormModel(D, 'item', owner, 'ar')!;
    expect(item.fields.find((x) => x.id === 'unit')).toMatchObject({ control: 'select' });
    expect(item.fields.find((x) => x.id === 'unit')!.options![1]!.label).toBe('كرتون');
    expect(buildFormModel(D, 'customer', owner, 'en')!.fields.find((x) => x.id === 'phone')).toMatchObject({ control: 'numeric', inputType: 'tel' });
  });
  it('is denied by default without the tools, a role or a record', () => {
    expect(buildFormModel(without('sales_order.create'), 'sales_order', rep, 'en')).toBeNull();
    expect(buildFormModel(D, 'sales_invoice', rep, 'en', 'INV-00001')).toBeNull();
    expect(buildFormModel(D, 'customer', rep, 'en', 'NOPE')).toBeNull();
    expect(buildFormModel(D, 'item', rep, 'en')).toBeNull(); // read-only role cannot create
    expect(buildFormModel(D, 'nothing', owner, 'en')).toBeNull();
  });
});

describe('action model and risk gating', () => {
  it('maps risk class to mode', () => {
    expect(modeFor('R0', true)).toBe('direct');
    expect(modeFor('R1', true)).toBe('direct');
    expect(modeFor('R2', true)).toBe('confirm');
    for (const r of ['R3', 'R4'] as const) expect(modeFor(r, true)).toBe('needs_approval');
    for (const r of ['R0', 'R1', 'R2'] as const) expect(modeFor(r, false)).toBe('needs_approval');
  });
  it('R3 and R4 tools are never executable by the UI', () => {
    const inv = D.entities.find((e) => e.id === 'sales_invoice')!;
    const a = buildActions({ entity: inv, tools: D.tools, caller: accountant, record: { id: 'INV-00001' } });
    const submit = a.find((x) => x.kind === 'submit')!;
    const cancel = a.find((x) => x.kind === 'cancel')!;
    expect([submit.risk, submit.mode, executable(submit)]).toEqual(['R3', 'needs_approval', false]);
    expect([cancel.risk, cancel.mode, executable(cancel)]).toEqual(['R4', 'needs_approval', false]);
    expect(a.find((x) => x.kind === 'edit')!.mode).toBe('direct');
  });
  it('agent_creatable=false needs approval even at low risk, and R2 needs a confirm step', () => {
    const so = D.entities.find((e) => e.id === 'sales_order')!;
    const wf = D.workflows[0];
    const approve = buildActions({ entity: so, workflow: wf, tools: D.tools, caller: owner, record: { id: 'SO-00002', state: 'pending_approval' } });
    expect(approve.map((a) => [a.id, a.mode])).toEqual([['transition:approve_large', 'needs_approval']]);
    const r2 = patch('customer.update', (t) => ({ ...t, risk_class: 'R2' }));
    const cust = r2.entities.find((e) => e.id === 'customer')!;
    expect(buildActions({ entity: cust, tools: r2.tools, caller: owner, record: { id: 'CUST-001' } })[0]).toMatchObject({ kind: 'edit', mode: 'confirm' });
  });
  it('offers only the transitions of the current status that the role may use', () => {
    const so = D.entities.find((e) => e.id === 'sales_order')!;
    const draft = buildActions({ entity: so, workflow: D.workflows[0], tools: D.tools, caller: rep, record: { id: 'SO-00001', state: 'draft' } });
    expect(draft.map((a) => a.id)).toEqual(['edit', 'submit:submit_small', 'submit:submit_large', 'cancel:cancel_draft']);
    const approved = buildActions({ entity: so, workflow: D.workflows[0], tools: D.tools, caller: rep, record: { id: 'SO-00003', state: 'approved' } });
    expect(approved).toEqual([]); // deliver is for the keeper and the owner
    expect(buildActions({ entity: so, workflow: D.workflows[0], tools: D.tools, caller: keeper, record: { id: 'SO-00003', state: 'approved' } }).map((a) => a.id)).toEqual(['submit:deliver']);
  });
  it('is deny by default: no tool, no action; amend needs its own tool', () => {
    const so = D.entities.find((e) => e.id === 'sales_order')!;
    expect(buildActions({ entity: so, tools: without('sales_order.create').tools, caller: rep })).toEqual([]);
    const noUpdate = buildActions({ entity: so, workflow: D.workflows[0], tools: without('sales_order.update').tools, caller: rep, record: { id: 'SO-00001', state: 'draft' } });
    expect(noUpdate.some((a) => a.kind === 'edit')).toBe(false);
    const locked = buildActions({ entity: so, workflow: D.workflows[0], tools: D.tools, caller: owner, record: { id: 'SO-00003', state: 'approved' } });
    expect(locked.some((a) => a.kind === 'amend' || a.kind === 'edit')).toBe(false);
    expect(buildActions({ entity: so, tools: D.tools, caller: { roleIds: [] } })).toEqual([]);
  });
  it('summarises only changed fields', () => {
    expect(summarizeChanges(['a', 'b', 'c'], { a: '1', b: 'x', c: '' }, { a: '1', b: 'y', c: 'z' })).toEqual([
      { fieldId: 'b', before: 'x', after: 'y' },
      { fieldId: 'c', before: '', after: 'z' },
    ]);
  });
});

describe('submitAction placeholder', () => {
  afterEach(() => vi.restoreAllMocks());
  const so = D.entities.find((e) => e.id === 'sales_order')!;
  it('returns a fixed result, never touches the network or the console, and refuses non-executable actions', async () => {
    const spies = [vi.spyOn(console, 'log'), vi.spyOn(console, 'info'), vi.spyOn(console, 'warn'), vi.spyOn(console, 'error'), vi.spyOn(globalThis, 'fetch')];
    const [ok] = buildActions({ entity: so, tools: D.tools, caller: rep });
    expect(await submitAction({ entityId: 'sales_order', action: ok!, values: { customer: 'secret-looking-value' } })).toEqual({ status: 'waiting_for_gateway' });
    const approval = buildActions({ entity: so, workflow: D.workflows[0], tools: D.tools, caller: owner, record: { id: 'SO-00002', state: 'pending_approval' } })[0]!;
    expect(await submitAction({ entityId: 'sales_order', recordId: 'SO-00002', action: approval, values: {} })).toEqual({ status: 'refused' });
    for (const s of spies) expect(s).not.toHaveBeenCalled();
  });
});
