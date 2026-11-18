// WEB-024: server-render the import and export screens in rtl and ltr.
import { describe, expect, it } from 'vitest';
import { renderToString } from 'react-dom/server';
import { NextIntlClientProvider } from 'next-intl';
import type { ReactElement } from 'react';
import { messages, type Locale } from '../../i18n';
import { fixtureData as D } from '../../records/fixture/rows';
import { ExportDialog } from './ExportDialog';
import { ImportWizard } from './ImportWizard';

const render = (l: Locale, node: ReactElement) =>
  renderToString(
    <div dir={l === 'ar' ? 'rtl' : 'ltr'}>
      <NextIntlClientProvider locale={l} messages={messages[l]} timeZone="UTC">{node}</NextIntlClientProvider>
    </div>,
  );

describe.each(['ar', 'en'] as const)('bulk screens in %s', (l) => {
  it('renders the upload step and the export preview with translated copy and no physical inline styles', () => {
    const imp = render(l, <ImportWizard data={D} entityId="customer" caller={{ roleIds: ['owner'] }} />);
    const exp = render(l, <ExportDialog data={D} entityId="customer" caller={{ roleIds: ['owner'] }} />);
    expect(imp).toContain(l === 'ar' ? 'ملف CSV' : 'CSV file');
    expect(exp).toContain(l === 'ar' ? 'تنزيل CSV' : 'Download CSV');
    for (const out of [imp, exp]) {
      expect(out.startsWith(`<div dir="${l === 'ar' ? 'rtl' : 'ltr'}"`)).toBe(true);
      for (const m of out.matchAll(/style="([^"]*)"/g)) expect(m[1]).not.toMatch(/(?:^|[;\s-])(?:left|right)\s*:|text-align|float/i);
      expect(out).not.toMatch(new RegExp(['frap','pe|erp','next'].join(''), 'i'));
    }
  });
  it('denies by default', () => {
    expect(render(l, <ImportWizard data={D} entityId="customer" caller={{ roleIds: ['accountant'] }} />)).toContain('role="alert"');
    expect(render(l, <ExportDialog data={D} entityId="customer" caller={{ roleIds: [] }} />)).toContain('role="alert"');
  });
});
