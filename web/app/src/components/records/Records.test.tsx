// WEB-023: server-render the record screens in rtl and ltr (same approach as ui/rtl.test.tsx; no jsdom).
import { describe, expect, it } from 'vitest';
import { renderToString } from 'react-dom/server';
import { NextIntlClientProvider } from 'next-intl';
import type { ReactElement } from 'react';
import { messages, type Locale } from '../../i18n';
import { fixtureData } from '../../records/fixture/rows';
import type { Caller } from '../../records/types';
import { ConfirmWrite } from './ConfirmWrite';
import { RecordForm } from './RecordForm';
import { RecordList } from './RecordList';
import { StatusBadge } from './StatusBadge';

const D = fixtureData;
const owner: Caller = { roleIds: ['owner'] };
const rep: Caller = { roleIds: ['sales_rep'] };
const accountant: Caller = { roleIds: ['accountant'] };
const dirOf = (l: Locale) => (l === 'ar' ? 'rtl' : 'ltr');
const render = (l: Locale, node: ReactElement) =>
  renderToString(
    <div dir={dirOf(l)}>
      <NextIntlClientProvider locale={l} messages={messages[l]} timeZone="UTC">{node}</NextIntlClientProvider>
    </div>,
  );
const inline = (out: string) => [...out.matchAll(/style="([^"]*)"/g)].map((m) => m[1]!);

describe.each(['rtl', 'ltr'] as const)('record screens in %s', (dir) => {
  const l: Locale = dir === 'rtl' ? 'ar' : 'en';
  const list = render(l, <RecordList data={D} entityId="sales_order" caller={owner} />);
  const form = render(l, <RecordForm data={D} entityId="customer" caller={owner} recordId="CUST-001" />);

  it('keeps the root direction and uses no physical inline styles', () => {
    for (const out of [list, form]) {
      expect(out.startsWith(`<div dir="${dir}"`)).toBe(true);
      for (const s of inline(out)) expect(s).not.toMatch(/(?:^|[;\s-])(?:left|right)\s*:|text-align|float/i);
    }
  });
  it('uses translated copy for the language', () => {
    expect(list).toContain(l === 'ar' ? 'أوامر البيع' : 'Sales orders');
    expect(list).toContain(l === 'ar' ? 'بحث' : 'Search');
    expect(form).toContain(l === 'ar' ? 'حد الائتمان' : 'Credit limit');
  });
  it('keeps numbers, amounts and dates left-to-right', () => {
    expect(list).toContain('<bdi dir="ltr" class="Records-module__num">1150.00 SAR</bdi>'.replace('Records-module__num', list.match(/<bdi dir="ltr" class="([^"]*)">1150\.00 SAR/)?.[1] ?? 'x'));
    expect(list).toMatch(/<bdi dir="ltr">2026-03-01<\/bdi>/);
    expect(form).toMatch(/<input[^>]*dir="ltr"[^>]*value="50000\.00"|<input[^>]*value="50000\.00"[^>]*dir="ltr"/);
    expect(form).toMatch(/<input[^>]*dir="auto"[^>]*value="Sample Trading Co"|<input[^>]*value="Sample Trading Co"[^>]*dir="auto"/);
  });
});

describe('record screens content', () => {
  it('lists rows with status badges and linked-record anchors', () => {
    const out = render('en', <RecordList data={D} entityId="sales_order" caller={owner} />);
    expect(out).toContain('href="/records/sales_order/SO-00001/"');
    expect(out).toContain('href="/records/customer/CUST-001/"');
    expect(out).toContain('Draft');
    expect(out).toContain('href="/records/sales_order/new/"');
  });
  it('shows nothing for a list the caller has no tool for, and no create link without a create tool', () => {
    expect(render('en', <RecordList data={D} entityId="sales_invoice" caller={rep} />)).toContain('You do not have access to this list.');
    expect(render('en', <RecordList data={D} entityId="item" caller={rep} />)).not.toContain('/records/item/new/');
  });
  it('does not render hidden fields', () => {
    const out = render('en', <RecordForm data={D} entityId="customer" caller={rep} recordId="CUST-001" />);
    expect(out).not.toContain('Credit limit');
    expect(out).not.toContain('50000.00');
  });
  it('denies a form without tools', () => {
    expect(render('en', <RecordForm data={D} entityId="sales_invoice" caller={rep} />)).toContain('You do not have access to this record.');
  });
  it('shows R3 and R4 actions as needs approval, disabled, with no way to run them', () => {
    const out = render('en', <RecordForm data={D} entityId="sales_invoice" caller={accountant} recordId="INV-00001" />);
    expect(out.match(/Needs approval/g)).toHaveLength(2);
    expect(out).toMatch(/<button[^>]*disabled[^>]*>Submit<\/button>/);
    expect(out).toMatch(/<button[^>]*disabled[^>]*>Cancel<\/button>/);
  });
  it('shows transition labels from the Blueprint and the record status', () => {
    const out = render('ar', <RecordForm data={D} entityId="sales_order" caller={rep} recordId="SO-00001" />);
    expect(out).toContain('إرسال للاعتماد');
    expect(out).toContain('مسودة');
  });
  it('renders the confirm step with a plain summary of the change', () => {
    const out = render('en', (
      <ConfirmWrite actionLabel="Save changes" entityLabel="Customer" recordId="CUST-001" risk="R2" sensitive
        changes={[{ fieldId: 'phone', label: 'Mobile', before: '+966500000001', after: '' }]} onConfirm={() => {}} onCancel={() => {}} />
    ));
    expect(out).toContain('role="dialog"');
    expect(out).toContain('Mobile: +966500000001 to empty');
    expect(out).toContain('Risk level: R2.');
    expect(out).toContain('Confirm');
    expect(render('ar', <ConfirmWrite actionLabel="x" entityLabel="y" risk="R2" sensitive={false} changes={[]} onConfirm={() => {}} onCancel={() => {}} />)).toContain('رجوع');
  });
  it('status badge carries text', () => {
    expect(render('en', <StatusBadge label="Draft" tone="danger" />)).toContain('Draft');
  });
  it('never names the engine in visible copy', () => {
    const all = [render('en', <RecordList data={D} entityId="customer" caller={owner} />), render('ar', <RecordForm data={D} entityId="sales_order" caller={owner} recordId="SO-00001" />), JSON.stringify(messages.en.records), JSON.stringify(messages.ar.records)].join(' ');
    expect(all).not.toMatch(new RegExp(['frap','pe|erp','next'].join(''), 'i'));
  });
});
