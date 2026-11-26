// WEB-029: the record detail view models (line items, totals, history) and digit grouping. Pure.
import { describe, expect, it } from 'vitest';
import { fixtureData as D } from './fixture/rows';
import { buildFormModel } from './formModel';
import { buildActivity, buildLines, groupDigits, splitTotals } from './detailModel';

const owner = { roleIds: ['owner'] };
const keeper = { roleIds: ['warehouse_keeper'] };
const nobody = { roleIds: ['guest'] };

describe('groupDigits', () => {
  it('groups the integer part and keeps the decimals exactly as given', () => {
    expect(groupDigits('1150.00')).toBe('1,150.00');
    expect(groupDigits('70380.00')).toBe('70,380.00');
    expect(groupDigits('1234567.5')).toBe('1,234,567.5');
    expect(groupDigits('-61200.00')).toBe('-61,200.00');
    expect(groupDigits('999')).toBe('999');
  });
  it('leaves anything that is not a plain decimal untouched', () => {
    expect(groupDigits('')).toBe('');
    expect(groupDigits('12a34')).toBe('12a34');
    expect(groupDigits('1e9')).toBe('1e9');
  });
});

describe('buildLines', () => {
  it('reads a child table from the parent record with Blueprint labels and linked names', () => {
    const [items] = buildLines(D, 'sales_order', owner, 'en', 'SO-00001');
    expect(items?.title).toBe('Items');
    expect(items?.columns.map((c) => c.label)).toEqual(['Item', 'Quantity', 'Rate', 'Amount']);
    expect(items?.columns.map((c) => c.numeric)).toEqual([false, true, true, true]);
    expect(items?.rows).toHaveLength(2);
    const first = items!.rows[0]!.cells;
    expect(first[0]).toMatchObject({ kind: 'link', text: 'Rice 5 kg', href: '/records/item/ITM-001/' });
    expect(first[3]).toMatchObject({ kind: 'money', money: { value: '490.00', currency: 'SAR' } });
  });
  it('uses the reader language', () => {
    expect(buildLines(D, 'sales_order', owner, 'ar', 'SO-00001')[0]?.columns[0]?.label).toBe('الصنف');
  });
  it('is empty for entities without a child table, a new record, or a caller who cannot open the record', () => {
    expect(buildLines(D, 'customer', owner, 'en', 'CUST-001')).toEqual([]);
    expect(buildLines(D, 'sales_order', owner, 'en')).toEqual([]);
    expect(buildLines(D, 'sales_order', nobody, 'en', 'SO-00001')).toEqual([]);
  });
  it('shows the linked id, not its name, when the caller cannot open the linked entity', () => {
    const accountant = { roleIds: ['accountant'] };
    const cell = buildLines(D, 'sales_order', accountant, 'en', 'SO-00001')[0]!.rows[0]!.cells[0]!;
    expect(cell.text).toBe('ITM-001');
    expect(cell.href).toBeUndefined();
  });
});

describe('splitTotals', () => {
  it('moves the read-only money fields of a document into the totals block, the last one as the grand total', () => {
    const model = buildFormModel(D, 'sales_order', owner, 'en', 'SO-00001')!;
    const { fields, totals } = splitTotals(D, model);
    expect(totals.map((x) => x.label)).toEqual(['Subtotal', 'VAT', 'Total']);
    expect(totals.map((x) => x.grand)).toEqual([false, false, true]);
    expect(totals[2]).toMatchObject({ value: '1150.00', currency: 'SAR' });
    expect(fields.map((f) => f.id)).toEqual(['customer', 'order_date']);
  });
  it('keeps master records whole', () => {
    const model = buildFormModel(D, 'customer', owner, 'en', 'CUST-001')!;
    expect(splitTotals(D, model).totals).toEqual([]);
  });
});

describe('buildActivity', () => {
  it('lists the history newest first with workflow state labels and tones', () => {
    const a = buildActivity(D, 'sales_order', keeper, 'ar', 'SO-00004');
    expect(a.map((x) => x.event)).toEqual(['state', 'state', 'created']);
    expect(a[0]).toMatchObject({ stateLabel: 'تم التسليم', tone: 'success', by: 'Omar Nasser', at: '2026-03-05T14:45:00Z' });
  });
  it('is empty for a caller who cannot open the record and for a new record', () => {
    expect(buildActivity(D, 'sales_order', nobody, 'en', 'SO-00001')).toEqual([]);
    expect(buildActivity(D, 'sales_order', owner, 'en')).toEqual([]);
  });
});
