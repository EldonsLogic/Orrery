// WEB-024: CSV reader/writer, import mapping and validation, export view model.
import { describe, expect, it } from 'vitest';
import { csvCell, parseCsv, toCsv } from './csv';
import { fixtureData as D } from './fixture/rows';
import { buildExportModel } from './exportModel';
import { autoMap, buildImportPlan, canRunImport, checkMapping, errorReportCsv, validValues, validateRows } from './importModel';
import { submitAction } from './submitAction';

const owner = { roleIds: ['owner'] };
const rep = { roleIds: ['sales_rep'] };
const accountant = { roleIds: ['accountant'] };

describe('csv', () => {
  it('reads quotes, doubled quotes, embedded newlines, BOM and CRLF', () => {
    expect(parseCsv('﻿a,b\r\n"x, y","He said ""hi"""\r\n"l1\nl2",z\r\n\r\n').rows).toEqual([['a', 'b'], ['x, y', 'He said "hi"'], ['l1\nl2', 'z']]);
  });
  it('detects semicolon and tab delimiters', () => {
    expect(parseCsv('a;b\n1;2').rows).toEqual([['a', 'b'], ['1', '2']]);
    expect(parseCsv('a\tb\n1\t2').rows[1]).toEqual(['1', '2']);
  });
  it('reports an unterminated quote', () => expect(parseCsv('a,b\n"x,y').error).toBe('unterminatedQuote'));
  it('neutralises spreadsheet formulas but leaves numbers alone', () => {
    expect(csvCell('=SUM(A1)')).toBe("'=SUM(A1)");
    expect(csvCell('@x')).toBe("'@x");
    expect(csvCell('-5.5')).toBe('-5.5');
    expect(toCsv([['a,b', 'c']])).toBe('"a,b",c\r\n');
  });
});

describe('import plan', () => {
  it('drops fields hidden for the caller and keeps the rest', () => {
    const p = buildImportPlan(D, 'customer', rep, 'en')!;
    expect(p.fields.map((f) => f.id)).toEqual(['customer_name', 'vat_number', 'phone']); // credit_limit hidden for sales_rep
    expect(buildImportPlan(D, 'customer', owner, 'en')!.fields.map((f) => f.id)).toContain('credit_limit');
  });
  it('denies without a create tool, and the bulk action always confirms', () => {
    expect(buildImportPlan(D, 'customer', accountant, 'en')).toBeNull();
    expect(buildImportPlan(D, 'nope', owner, 'en')).toBeNull();
    const p = buildImportPlan(D, 'customer', owner, 'en')!;
    expect(p.action).toMatchObject({ risk: 'R2', mode: 'confirm', id: 'bulk_import' });
    expect(canRunImport(p)).toBe(true);
  });
  it('maps headers by id or label in any language, once each, and flags missing required fields', () => {
    const p = buildImportPlan(D, 'customer', owner, 'en')!;
    expect(autoMap(['Customer name', 'الجوال', 'phone', 'junk'], p, D)).toEqual(['customer_name', 'phone', null, null]);
    expect(checkMapping([null, 'phone'], p)).toEqual([{ code: 'missingRequired', fieldId: 'customer_name' }]);
    expect(checkMapping(['phone', 'phone', 'customer_name'], p)[0]).toEqual({ code: 'duplicate', fieldId: 'phone' });
  });
});

describe('row validation', () => {
  const p = buildImportPlan(D, 'customer', owner, 'en')!;
  const map = ['customer_name', 'phone', 'credit_limit'];
  it('accepts valid rows, normalises Arabic digits, rejects bad ones with line numbers', () => {
    const r = validateRows([['Acme', '٠٥٠٠٠٠٠٠٠١', '1,200.50'], ['', 'abc', '1.234'], ['Beta', '', 'x']], map, p, D);
    expect(r.validCount).toBe(1);
    expect(r.rows[0]!.values).toMatchObject({ phone: '0500000001', credit_limit: '1200.50' });
    expect(r.rows[1]).toMatchObject({ line: 3 });
    expect(r.rows[1]!.errors.map((e) => e.code)).toEqual(['required', 'notPhone', 'tooPrecise']);
    expect(r.rows[2]!.errors.map((e) => e.code)).toEqual(['notNumber']);
    expect(validValues(r)).toEqual([r.rows[0]!.values]);
  });
  it('never carries values for unmapped or hidden fields', () => {
    const rp = buildImportPlan(D, 'customer', rep, 'en')!;
    const r = validateRows([['Acme', '999']], ['customer_name', 'credit_limit'], rp, D); // credit_limit is not importable for rep
    expect(Object.keys(r.rows[0]!.values)).not.toContain('credit_limit');
  });
  it('checks links against known records, dates and options', () => {
    const op = buildImportPlan(D, 'sales_order', owner, 'en')!;
    const r = validateRows([['CUST-001', '2026-02-30'], ['CUST-999', '2026-03-01']], ['customer', 'order_date'], op, D);
    expect(r.rows[0]!.errors.map((e) => e.code)).toEqual(['notDate']);
    expect(r.rows[1]!.errors.map((e) => e.code)).toEqual(['notLink']);
    const ip = buildImportPlan(D, 'item', owner, 'en')!;
    expect(validateRows([['Rice', 'RICE', 'carton']], ['item_name', 'item_code', 'unit'], ip, D).rows[0]!.values.unit).toBe('carton');
  });
  it('writes an error report as CSV with the problem per line', () => {
    const r = validateRows([['', '1']], ['customer_name', 'phone'], p, D);
    const csv = errorReportCsv(r, (id) => id, (c) => c, { line: 'Line', field: 'Field', problem: 'Problem', value: 'Value' });
    expect(csv).toBe('Line,Field,Problem,Value\r\n2,customer_name,required,\r\n2,phone,notPhone,1\r\n');
  });
});

describe('export model', () => {
  it('omits hidden fields and denies without a list tool', () => {
    expect(buildExportModel(D, 'customer', rep, 'en', 'No.')!.headers).not.toContain('Credit limit');
    const o = buildExportModel(D, 'customer', owner, 'en', 'No.')!;
    expect(o.headers).toContain('Credit limit');
    expect(o.csv.split('\r\n')[1]).toContain('CUST-001');
    expect(buildExportModel(D, 'customer', { roleIds: [] }, 'en', 'No.')).toBeNull();
  });
});

describe('bulk write', () => {
  it('goes through the placeholder and never executes', async () => {
    const p = buildImportPlan(D, 'customer', owner, 'en')!;
    expect(await submitAction({ entityId: 'customer', action: p.action!, values: {}, rows: [{ customer_name: 'A' }] })).toEqual({ status: 'waiting_for_gateway' });
  });
});
