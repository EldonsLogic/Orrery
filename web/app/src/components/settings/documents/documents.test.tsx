// WEB-009: server-render the document templates screen in both languages (same approach as branding.test.tsx; no jsdom).
import { describe, expect, it } from 'vitest';
import { renderToString } from 'react-dom/server';
import { NextIntlClientProvider } from 'next-intl';
import { messages } from '../../../i18n';
import { fixtureBlueprint } from '../../../blueprint/fixture';
import { createDocumentTemplatesController } from '../../../settings/documents/controller';
import { canEditDocumentTemplates } from '../../../settings/documents/access';
import { DEFAULT_TEMPLATES, LOCKED_REGIONS, TEMPLATE_KINDS, checkTemplate, createFakeDocumentTemplatesPort } from '../../../settings/documents/port';
import { DocumentTemplatesEditor } from './DocumentTemplatesScreen';

const ENGINE = new RegExp(['fra' + 'ppe', 'ERP' + 'Next'].join('|'), 'i');
const wrap = (locale: 'ar' | 'en', node: React.ReactNode) =>
  renderToString(
    <div dir={locale === 'ar' ? 'rtl' : 'ltr'}>
      <NextIntlClientProvider locale={locale} messages={messages[locale]}>
        {node}
      </NextIntlClientProvider>
    </div>,
  );
const view = (locale: 'ar' | 'en', kind?: (typeof TEMPLATE_KINDS)[number]) =>
  wrap(locale, <DocumentTemplatesEditor port={createFakeDocumentTemplatesPort()} initial={DEFAULT_TEMPLATES} initialKind={kind} />);

describe('document templates screen', () => {
  it.each(['ar', 'en'] as const)('lists the three templates, locked regions and a preview (%s)', (l) => {
    const out = view(l);
    const t = messages[l].documents;
    expect(out.match(/<h1/g)).toHaveLength(1);
    for (const k of TEMPLATE_KINDS) expect(out).toContain(t.kinds[k]);
    expect(out).toContain(t.locked.title);
    expect(out).toContain(t.preview.title);
    expect(out).toContain(`dir="${l === 'ar' ? 'rtl' : 'ltr'}"`);
    expect(out).not.toMatch(ENGINE);
  });
  it('the Arabic screen uses no English catalogue text', () => {
    const out = view('ar');
    expect(out).not.toContain(messages.en.documents.title);
    expect(out).toContain(messages.ar.documents.title);
  });
  it('shows every locked region of the tax invoice as locked, in the controls and in the preview', () => {
    const out = view('en', 'tax_invoice');
    for (const r of LOCKED_REGIONS.tax_invoice) expect(out).toContain(messages.en.documents.regions[r as keyof typeof messages.en.documents.regions]);
    expect(out.match(/data-locked-region=/g)?.length).toBe(LOCKED_REGIONS.tax_invoice.length * 2);
    expect(out).toContain(messages.en.documents.locked.note);
  });
  it('footer text is untrusted: markup and bidi overrides are shown as plain text', () => {
    const initial = { ...DEFAULT_TEMPLATES, quote: { ...DEFAULT_TEMPLATES.quote, footerText: '<script>x()</script>\u202e' } };
    const out = wrap('en', <DocumentTemplatesEditor port={createFakeDocumentTemplatesPort()} initial={initial} initialKind="quote" />);
    expect(out).not.toContain('<script>');
    // The preview shows the override as a visible marker; the field flags the value and Save is off.
    expect(out).toContain('&lt;script&gt;x()&lt;/script&gt;&lt;U+202E&gt;</p>');
    expect(out).toContain(messages.en.documents.footer.invalid);
    expect(out).toMatch(/<button[^>]*disabled/);
  });
  it('shows loading and disables saving until stored settings load', () => {
    const out = wrap('en', <DocumentTemplatesEditor port={createFakeDocumentTemplatesPort()} initial={null} />);
    expect(out).toContain(messages.en.documents.loading);
    expect(out).toMatch(/<button[^>]*disabled/);
  });
});

describe('document templates access, port and controller', () => {
  it('only an administrator role may edit (deny by default)', () => {
    expect(canEditDocumentTemplates(fixtureBlueprint, { roleIds: ['owner'] })).toBe(true);
    expect(canEditDocumentTemplates(fixtureBlueprint, { roleIds: ['sales_rep'] })).toBe(false);
    expect(canEditDocumentTemplates(fixtureBlueprint, { roleIds: [] })).toBe(false);
  });
  it('checkTemplate refuses unknown tokens, placements and unsafe or long footers', () => {
    expect(checkTemplate(DEFAULT_TEMPLATES.quote)).toBe(true);
    expect(checkTemplate({ ...DEFAULT_TEMPLATES.quote, accent: 'red' as never })).toBe(false);
    expect(checkTemplate({ ...DEFAULT_TEMPLATES.quote, logoPlacement: 'left' as never })).toBe(false);
    expect(checkTemplate({ ...DEFAULT_TEMPLATES.quote, footerText: 'a'.repeat(201) })).toBe(false);
    expect(checkTemplate({ ...DEFAULT_TEMPLATES.quote, footerText: 'x‮y' })).toBe(false);
  });
  it('the fake port saves valid settings and refuses invalid ones', async () => {
    const port = createFakeDocumentTemplatesPort();
    expect(await port.save(DEFAULT_TEMPLATES)).toEqual({ ok: true });
    expect(port.saved).toHaveLength(1);
    const bad = { ...DEFAULT_TEMPLATES, quote: { ...DEFAULT_TEMPLATES.quote, footerText: 'a'.repeat(500) } };
    expect(await port.save(bad)).toEqual({ ok: false, code: 'invalid' });
  });
  it('edits one template and saves all through the port', async () => {
    const port = createFakeDocumentTemplatesPort();
    const c = createDocumentTemplatesController(port, DEFAULT_TEMPLATES);
    c.attach();
    c.edit('purchase_order', { logoPlacement: 'center' });
    expect(c.get().settings.purchase_order.logoPlacement).toBe('center');
    expect(c.get().settings.quote).toEqual(DEFAULT_TEMPLATES.quote);
    await c.save();
    expect(c.get().status).toBe('saved');
    expect(port.saved[0]?.purchase_order.logoPlacement).toBe('center');
  });
  it('a result arriving after detach is dropped', async () => {
    let done: (r: { ok: true }) => void = () => {};
    const port = { ...createFakeDocumentTemplatesPort(), save: () => new Promise<{ ok: true }>((r) => (done = r)) };
    const c = createDocumentTemplatesController(port, DEFAULT_TEMPLATES);
    const off = c.attach();
    const p = c.save();
    off();
    done({ ok: true });
    await p;
    expect(c.get().status).toBe('saving');
  });
  it('does not allow edits before load, and a failed load keeps saving off', async () => {
    const port = { ...createFakeDocumentTemplatesPort(), load: () => Promise.reject(new Error('x')) };
    const c = createDocumentTemplatesController(port, null);
    c.attach();
    c.edit('quote', { footerText: 'hi' });
    expect(c.get().settings.quote.footerText).toBe(DEFAULT_TEMPLATES.quote.footerText);
    await new Promise((r) => setTimeout(r, 0));
    expect(c.get().loaded).toBe('failed');
    await c.save();
    expect(c.get().status).toBe('idle');
  });
});
