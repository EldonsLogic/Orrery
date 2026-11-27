// WEB-009: server-render the document templates screen in both languages (same approach as branding.test.tsx; no jsdom).
import fs from 'node:fs';
import { describe, expect, it } from 'vitest';
import { renderToString } from 'react-dom/server';
import { NextIntlClientProvider } from 'next-intl';
import { messages } from '../../../i18n';
import { fixtureBlueprint } from '../../../blueprint/fixture';
import { fixtureSession, type SessionState } from '../../../lib/session';
import { SessionProvider } from '../../shell/SessionProvider';
import { createDocumentTemplatesController } from '../../../settings/documents/controller';
import { canEditDocumentTemplates } from '../../../settings/documents/access';
import { DEFAULT_TEMPLATES, LOCKED_REGIONS, TEMPLATE_KINDS, checkTemplate, createFakeDocumentTemplatesPort } from '../../../settings/documents/port';
import { DocumentTemplatesEditor, DocumentTemplatesScreen } from './DocumentTemplatesScreen';

const ENGINE = new RegExp(['fra' + 'ppe', 'ERP' + 'Next'].join('|'), 'i');
const wrap = (locale: 'ar' | 'en', node: React.ReactNode) =>
  renderToString(
    <div dir={locale === 'ar' ? 'rtl' : 'ltr'}>
      <NextIntlClientProvider locale={locale} messages={messages[locale]}>
        {node}
      </NextIntlClientProvider>
    </div>,
  );
const view = (locale: 'ar' | 'en', kind?: (typeof TEMPLATE_KINDS)[number], initial = DEFAULT_TEMPLATES) =>
  wrap(locale, <DocumentTemplatesEditor port={createFakeDocumentTemplatesPort()} initial={initial} initialKind={kind} />);

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
  it.each(TEMPLATE_KINDS)('%s keeps the footer as a locked region, last, in the controls and in the preview', (kind) => {
    const regions = LOCKED_REGIONS[kind];
    expect(regions[regions.length - 1]).toBe('footer');
    const out = view('en', kind);
    expect(out.match(/data-locked-region=/g)?.length).toBe(regions.length * 2);
    expect(out.match(/data-locked-region="footer"/g)).toHaveLength(2);
    expect(out).toContain(messages.en.documents.locked.note);
  });
  it('the tenant footer text sits inside the locked footer region and follows the viewer language', () => {
    const initial = { ...DEFAULT_TEMPLATES, footerText: { ar: 'شكرا لتعاملكم', en: 'Thank you for your business' } };
    const en = view('en', 'quote', initial);
    const preview = en.slice(en.lastIndexOf('data-locked-region="footer"'));
    expect(preview).toContain('Thank you for your business');
    expect(preview).not.toContain('شكرا لتعاملكم');
    expect(view('ar', 'quote', initial)).toContain('شكرا لتعاملكم');
  });
  it('footer text is untrusted: markup and bidi overrides are shown as plain text', () => {
    const initial = { ...DEFAULT_TEMPLATES, footerText: { ar: 'x', en: '<script>x()</script>‮' } };
    const out = view('en', 'quote', initial);
    expect(out).not.toContain('<script>');
    expect(out).toContain('&lt;script&gt;x()&lt;/script&gt;&lt;U+202E&gt;</span>');
    expect(out).toContain(messages.en.documents.footer.invalid);
    expect(out).toMatch(/<button[^>]*disabled/);
  });
  it('a footer filled in one language only is flagged and cannot be saved', () => {
    const out = view('en', 'quote', { ...DEFAULT_TEMPLATES, footerText: { ar: '', en: 'Hello' } });
    expect(out).toContain(messages.en.documents.footer.both);
    expect(out).toMatch(/<button[^>]*disabled/);
  });
  it('shows loading and disables saving until stored settings load', () => {
    const out = wrap('en', <DocumentTemplatesEditor port={createFakeDocumentTemplatesPort()} initial={null} />);
    expect(out).toContain(messages.en.documents.loading);
    expect(out).toMatch(/<button[^>]*disabled/);
  });
});

describe('document templates colour use', () => {
  const css = fs.readFileSync(new URL('./DocumentTemplatesScreen.module.css', import.meta.url), 'utf8');
  it('never uses the accent token as a text colour (WCAG 1.4.3: it is for graphics only)', () => {
    expect(css).not.toMatch(/(^|[;{\s])color:\s*var\(--color-accent\)/);
    expect(css).not.toContain('--doc-accent');
  });
  it('has the screen colour pairs in the contrast check', async () => {
    const { PAIRS_ALL } = await import('../../../../../scripts/check-contrast.mjs');
    const ids = (PAIRS_ALL as { id: string; file: string }[]).filter((p) => p.file.includes('DocumentTemplatesScreen')).map((p) => p.id);
    expect(ids).toEqual(expect.arrayContaining(['doc-region-name/surface', 'doc-table-head', 'doc-rule/surface']));
  });
});

describe('document templates screen with a session', () => {
  const as = (tenantId: string, roles: string[]): SessionState =>
    fixtureSession.status === 'ready' ? { ...fixtureSession, claims: { ...fixtureSession.claims, tenantId, roles } } : fixtureSession;
  const mount = (session: SessionState, portFor: (id: string) => ReturnType<typeof createFakeDocumentTemplatesPort>) =>
    renderToString(
      <NextIntlClientProvider locale="en" messages={messages.en}>
        <SessionProvider initial={session}>
          <DocumentTemplatesScreen portFor={portFor} />
        </SessionProvider>
      </NextIntlClientProvider>,
    );
  it('asks for a separate port per active workspace', () => {
    const asked: string[] = [];
    const portFor = (id: string) => (asked.push(id), createFakeDocumentTemplatesPort());
    for (const tenantId of ['tenant-fixture-a', 'tenant-fixture-b']) mount(as(tenantId, ['owner']), portFor);
    expect(asked).toEqual(['tenant-fixture-a', 'tenant-fixture-b']);
  });
  it('denies a non-administrator: no editor, no save, no port data requested for editing', () => {
    const out = mount(as('tenant-fixture-a', ['sales_rep']), () => createFakeDocumentTemplatesPort());
    expect(out).toContain(messages.en.documents.noAccess.title);
    expect(out).toContain(messages.en.documents.noAccess.body);
    expect(out).not.toContain(messages.en.documents.save);
    expect(out).not.toContain('data-locked-region');
  });
  it('an administrator gets the editor', () => {
    const out = mount(as('tenant-fixture-a', ['owner']), () => createFakeDocumentTemplatesPort());
    expect(out).toContain(messages.en.documents.locked.title);
    expect(out).not.toContain(messages.en.documents.noAccess.title);
  });
});

describe('document templates access, port and controller', () => {
  it('only an administrator role may edit (deny by default)', () => {
    expect(canEditDocumentTemplates(fixtureBlueprint, { roleIds: ['owner'] })).toBe(true);
    expect(canEditDocumentTemplates(fixtureBlueprint, { roleIds: ['sales_rep'] })).toBe(false);
    expect(canEditDocumentTemplates(fixtureBlueprint, { roleIds: [] })).toBe(false);
  });
  it('checkTemplate matches the contract: known position, boolean flag, bilingual plain footer', () => {
    expect(checkTemplate(DEFAULT_TEMPLATES)).toBe(true);
    expect(checkTemplate({ ...DEFAULT_TEMPLATES, footerText: { ar: 'مرحبا', en: 'Hello' } })).toBe(true);
    expect(checkTemplate({ ...DEFAULT_TEMPLATES, logoPosition: 'left' as never })).toBe(false);
    expect(checkTemplate({ ...DEFAULT_TEMPLATES, accentOnDocuments: 'red' as never })).toBe(false);
    expect(checkTemplate({ ...DEFAULT_TEMPLATES, footerText: { ar: '', en: 'Hello' } })).toBe(false);
    expect(checkTemplate({ ...DEFAULT_TEMPLATES, footerText: { ar: 'a', en: 'a'.repeat(201) } })).toBe(false);
    expect(checkTemplate({ ...DEFAULT_TEMPLATES, footerText: { ar: 'x', en: 'x‮y' } })).toBe(false);
    expect(checkTemplate({ ...DEFAULT_TEMPLATES, footerText: undefined as never })).toBe(false);
  });
  it('the fake port saves valid settings and refuses invalid ones', async () => {
    const port = createFakeDocumentTemplatesPort();
    expect(await port.save(DEFAULT_TEMPLATES)).toEqual({ ok: true });
    expect(port.saved).toHaveLength(1);
    const bad = { ...DEFAULT_TEMPLATES, footerText: { ar: 'a', en: 'a'.repeat(500) } };
    expect(await port.save(bad)).toEqual({ ok: false, code: 'invalid' });
  });
  it('edits the settings and saves them through the port', async () => {
    const port = createFakeDocumentTemplatesPort();
    const c = createDocumentTemplatesController(port, DEFAULT_TEMPLATES);
    c.attach();
    c.edit({ logoPosition: 'center', accentOnDocuments: true });
    expect(c.get().settings).toMatchObject({ logoPosition: 'center', accentOnDocuments: true });
    await c.save();
    expect(c.get().status).toBe('saved');
    expect(port.saved[0]?.logoPosition).toBe('center');
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
    c.edit({ logoPosition: 'end' });
    expect(c.get().settings.logoPosition).toBe(DEFAULT_TEMPLATES.logoPosition);
    await new Promise((r) => setTimeout(r, 0));
    expect(c.get().loaded).toBe('failed');
    await c.save();
    expect(c.get().status).toBe('idle');
  });
});
