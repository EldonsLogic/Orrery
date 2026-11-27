// WEB-029: the records, detail, import/export and branding settings design pass. Server-rendered, no jsdom.
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { renderToString } from 'react-dom/server';
import { NextIntlClientProvider } from 'next-intl';
import type { ReactElement } from 'react';
import { messages, type Locale } from '../../i18n';
import { fixtureData as D } from '../../records/fixture/rows';
import { ConfirmWrite } from './ConfirmWrite';
import { ExportDialog } from './ExportDialog';
import { ImportWizard } from './ImportWizard';
import { RecordForm } from './RecordForm';
import { RecordList, RecordListSkeleton } from './RecordList';
import { SettingsLayout } from '../settings/SettingsLayout';

const owner = { roleIds: ['owner'] };
const render = (l: Locale, node: ReactElement) =>
  renderToString(
    <div dir={l === 'ar' ? 'rtl' : 'ltr'}>
      <NextIntlClientProvider locale={l} messages={messages[l]} timeZone="UTC">{node}</NextIntlClientProvider>
    </div>,
  );
const css = (f: string) => readFileSync(join(__dirname, f), 'utf8');
const ENGINE = new RegExp(['frap', 'pe|erp', 'next'].join(''), 'i');

describe('records list', () => {
  const en = render('en', <RecordList data={D} entityId="sales_order" caller={owner} />);
  const ar = render('ar', <RecordList data={D} entityId="sales_order" caller={owner} />);

  it('shows status as a word with an icon', () => {
    expect(en).toMatch(/data-tone="neutral"[^>]*>.*?<svg[^>]*data-icon="statusOpen".*?Draft/);
    expect(en).toContain('data-icon="statusStopped"');
  });
  it('groups figures, keeps them left-to-right and mutes the currency code', () => {
    for (const out of [en, ar]) expect(out).toMatch(/<bdi dir="ltr" class="[^"]*money[^"]*"><span class="[^"]*figure[^"]*">70,380\.00<\/span> <span class="[^"]*currency[^"]*">SAR<\/span><\/bdi>/);
  });
  it('has a toolbar with a labelled search and compact filters', () => {
    expect(en).toContain('placeholder="Search by number or name"');
    expect(en).toMatch(/<label[^>]*>.*?Search<\/span>/);
    expect(en).toContain('Status: all');
    expect(ar).toContain('الحالة: الكل');
  });
  it('renders stacked cards for phones beside the table, each card linking to its record', () => {
    expect(en).toMatch(/<ul[^>]*data-layout="cards"/);
    expect(en.match(/href="\/records\/sales_order\/SO-00002\/"/g)!.length).toBeGreaterThanOrEqual(2);
  });
  it('marks the sorted column for assistive technology', () => {
    const sorted = render('en', <RecordList data={D} entityId="sales_order" caller={owner} initialQuery={{ sort: { field: 'total_amount', direction: 'desc' } }} />);
    expect(sorted).toContain('aria-sort="descending"');
  });
  it('shows one page without a pager, and a range with pages when there are more', () => {
    expect(en).toMatch(/<bdi dir="ltr"[^>]*>1–6<\/bdi> of 6/);
    expect(en).not.toContain('>Next<');
    const paged = render('en', <RecordList data={D} entityId="sales_order" caller={owner} initialQuery={{ pageSize: 2 }} />);
    expect(paged).toMatch(/>1–2<\/bdi> of 6/);
    expect(paged).toMatch(/<nav[^>]*aria-label="Pages"/);
  });
  it('has empty states with a way out', () => {
    const none = render('en', <RecordList data={D} entityId="sales_order" caller={owner} initialQuery={{ search: 'zzz' }} />);
    expect(none).toContain('No records match');
    expect(none).toContain('Clear search and filters');
    expect(render('en', <RecordList data={{ ...D, rows: { ...D.rows, customer: [] } }} entityId="customer" caller={owner} />)).toContain('Nothing here yet');
  });
  it('has a loading skeleton that says what it is', () => {
    const out = render('en', <RecordListSkeleton />);
    expect(out).toContain('aria-busy="true"');
    expect(out).toContain('Loading records');
  });
  it('keeps the table header sticky and rows 40 high from the tokens', () => {
    const sheet = css('../../ui/Table.module.css');
    expect(sheet).toMatch(/thead \.cell \{[^}]*position: sticky/);
    expect(sheet).toContain('block-size: var(--row-compact)');
  });
});

describe('record detail', () => {
  const en = render('en', <RecordForm data={D} entityId="sales_order" caller={owner} recordId="SO-00002" />);
  const ar = render('ar', <RecordForm data={D} entityId="sales_order" caller={owner} recordId="SO-00002" />);

  it('has a header with a way back, the record number, its status and the actions', () => {
    expect(en).toContain('href="/records/sales_order/"');
    expect(en).toMatch(/<h1[^>]*>.*SO‑00002.*<\/h1>/);
    expect(en).toContain('Pending approval');
    expect(en).toMatch(/role="group" aria-label="Record actions"/);
  });
  it('shows the line items with Blueprint labels and linked names', () => {
    expect(en).toContain('Items');
    expect(en).toContain('Cooking oil carton');
    expect(ar).toContain('الكمية');
    expect(ar).toMatch(/57,600\.00/);
  });
  it('aligns a totals block with the grand total last', () => {
    expect(en).toMatch(/<dl[^>]*totals[^>]*>.*Subtotal.*61,200\.00.*VAT.*9,180\.00.*data-grand="true".*Total.*70,380\.00/s);
  });
  it('has an activity panel with people and state changes in words', () => {
    expect(en).toContain('Activity');
    expect(en).toContain('Omar Nasser');
    expect(ar).toContain('نقله');
    expect(en).toMatch(/<time dateTime="2026-03-02T09:02:00Z"/);
  });
  it('shows read-only values as text, not disabled inputs', () => {
    expect(en).not.toMatch(/<input[^>]*value="61200\.00"/);
  });
  it('never names the engine, a tool or a risk code', () => {
    for (const out of [en, ar]) {
      expect(out).not.toMatch(ENGINE);
      expect(out).not.toContain('sales_order.transition');
    }
    const confirm = render('en', <ConfirmWrite actionLabel="Save" entityLabel="Customer" recordId="CUST-001" risk="R2" sensitive={false} changes={[]} onConfirm={() => {}} onCancel={() => {}} />);
    expect(confirm).not.toContain('R2');
    expect(confirm).toContain('Risk: medium.');
  });
});

describe('import and export', () => {
  it('lays the import out in numbered steps with a drop zone', () => {
    const out = render('en', <ImportWizard data={D} entityId="customer" caller={owner} />);
    expect(out).toMatch(/<ol[^>]*aria-label="Import steps"/);
    expect(out).toMatch(/aria-current="step"[^>]*>.*?Upload/);
    expect(out).toContain('Step 1 of 4');
    expect(out).toContain('Drop a CSV file here');
    expect(out).toContain('accept=".csv,text/csv"');
    const ar = render('ar', <ImportWizard data={D} entityId="customer" caller={owner} />);
    expect(ar).not.toMatch(/[٠-٩]/); // one digit system: no Arabic-Indic digits mixed in
  });
  it('summarises the export before the download', () => {
    const out = render('en', <ExportDialog data={D} entityId="customer" caller={owner} />);
    expect(out).toMatch(/<dl[^>]*>.*Records.*3.*Columns.*5.*Format.*CSV/s);
  });
});

describe('settings layout', () => {
  it('has a section nav beside the content with the current page marked', () => {
    const out = render('en', <SettingsLayout active="branding"><p>content</p></SettingsLayout>);
    expect(out).toMatch(/<nav[^>]*aria-label="Settings sections"/);
    expect(out).toMatch(/<a[^>]*href="\/settings\/branding\/"[^>]*aria-current="page"/);
    expect(out).not.toContain('<h1');
    expect(render('ar', <SettingsLayout active="branding"><p>x</p></SettingsLayout>)).toContain('الهوية');
  });
});
