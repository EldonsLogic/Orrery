// WEB-007: server-render the branding screen in both languages (same approach as blueprint.test.tsx; no jsdom).
import { describe, expect, it } from 'vitest';
import { renderToString } from 'react-dom/server';
import { NextIntlClientProvider } from 'next-intl';
import data from '../../../settings/branding/colour.data.json';
import { DEFAULT_PRIMARY } from '../../../settings/branding/colour';
import { messages } from '../../../i18n';
import { fixtureBlueprint } from '../../../blueprint/fixture';
import type { Blueprint } from '../../../blueprint/types';
import { createBrandingController } from '../../../settings/branding/controller';
import { fixtureSession, type SessionState } from '../../../lib/session';
import { SessionProvider } from '../../shell/SessionProvider';
import type { BrandingPort, BrandingSettings } from '../../../settings/branding/port';
import { canEditBranding } from '../../../settings/branding/access';
import { checkLogo, createFakeBrandingPort } from '../../../settings/branding/port';
import { BrandingEditor, BrandingScreen } from './BrandingScreen';

const S = data.samples;
const ENGINE = new RegExp(['fra' + 'ppe', 'ERP' + 'Next'].join('|'), 'i');
const view = (locale: 'ar' | 'en', primary: string) =>
  renderToString(
    <div dir={locale === 'ar' ? 'rtl' : 'ltr'}>
      <NextIntlClientProvider locale={locale} messages={messages[locale]}>
        <BrandingEditor port={createFakeBrandingPort()} initial={{ primary, logo: null }} />
      </NextIntlClientProvider>
    </div>,
  );

describe('branding screen', () => {
  it.each(['ar', 'en'] as const)('renders both previews, a labelled pair table and one h1 (%s)', (l) => {
    const out = view(l, S.teal);
    const t = messages[l].branding;
    expect(out.match(/<h1/g)).toHaveLength(1);
    expect(out).toContain(t.preview.light);
    expect(out).toContain(t.preview.dark);
    expect(out.match(/<table/g)).toHaveLength(2);
    expect(out).toContain('scope="col"');
    expect(out).toContain('--color-primary:');
    expect(out).toContain(t.result.pass);
    expect(out).not.toMatch(ENGINE);
  });
  it('shows the rejection message and disables Save for an unusable colour', () => {
    const out = view('en', S.grey);
    expect(out).toContain(messages.en.branding.reject.grey);
    expect(out).not.toContain('<table');
    expect(out).toMatch(/<button[^>]*disabled/);
  });
  it('never renders an uploaded file: the file input is raster only', () => {
    const out = view('en', DEFAULT_PRIMARY);
    expect(out).toContain('accept="image/png,image/jpeg"');
    expect(out).not.toContain('<img');
  });
});

describe('branding review fixes', () => {
  it('hex field uses a text keypad (A-F reachable), ltr, with a pattern', () => {
    const out = view('en', S.teal);
    expect(out).not.toContain('inputMode="decimal"');
    expect(out).toContain('pattern=');
    expect(out).toMatch(/dir="ltr"/);
  });
  it('Save is disabled until stored branding has loaded', () => {
    const out = renderToString(
      <NextIntlClientProvider locale="en" messages={messages.en}>
        <BrandingEditor port={createFakeBrandingPort()} initial={null} />
      </NextIntlClientProvider>,
    );
    expect(out).toMatch(/<button[^>]*disabled/);
    expect(out).toContain(messages.en.branding.loading);
  });
  it('the preview link is not a dead tab stop and the result column has its own header', () => {
    const out = view('en', S.teal);
    expect(out).not.toContain('<a ');
    expect(out).toContain(messages.en.branding.result.result);
  });
});

describe('branding design fixes (WEB-029)', () => {
  it.each(['ar', 'en'] as const)('the logo control is a styled, translated file button with no native button text (%s)', (l) => {
    const out = view(l, S.teal);
    const t = messages[l].branding.logo;
    expect(out).toContain(t.choose);
    expect(out).toContain(t.none);
    expect(out).toMatch(/<label[^>]*data-file-button="true"/);
    expect(out).toMatch(/<input[^>]*type="file"[^>]*accept="image\/png,image\/jpeg"/);
  });
  it('the primary colour label shows once: the field label is for assistive technology only', () => {
    const out = view('en', S.teal);
    expect(out).toContain('data-label-hidden="true"');
  });
});

describe('branding access and port', () => {
  const withRoles = (patch: Record<string, { isAdmin?: boolean }>): Blueprint => ({
    ...fixtureBlueprint,
    roles: fixtureBlueprint.roles.map((r) => ({ ...r, ...(patch[r.id] ?? {}) })),
  });
  it('a general manager without isAdmin cannot edit, even though the role sees everything', () => {
    expect(fixtureBlueprint.roles.find((r) => r.id === 'general_manager')?.isAdmin).not.toBe(true);
    expect(canEditBranding(fixtureBlueprint, { roleIds: ['general_manager'] })).toBe(false);
    expect(canEditBranding(withRoles({ general_manager: { isAdmin: false } }), { roleIds: ['general_manager'] })).toBe(false);
  });
  it('a delegated admin with a different role may edit; an unrelated role and a mixed caller follow isAdmin', () => {
    const bp = withRoles({ sales_rep: { isAdmin: true } });
    expect(canEditBranding(bp, { roleIds: ['sales_rep'] })).toBe(true);
    expect(canEditBranding(bp, { roleIds: ['accountant', 'sales_rep'] })).toBe(true);
    expect(canEditBranding(bp, { roleIds: ['accountant'] })).toBe(false);
    expect(canEditBranding(withRoles({ owner: { isAdmin: false } }), { roleIds: ['owner'] })).toBe(false);
  });
  it('only roles with isAdmin may edit (deny by default)', () => {
    expect(canEditBranding(fixtureBlueprint, { roleIds: ['owner'] })).toBe(true);
    expect(canEditBranding(fixtureBlueprint, { roleIds: ['sales_rep'] })).toBe(false);
    expect(canEditBranding(fixtureBlueprint, { roleIds: [] })).toBe(false);
    expect(canEditBranding(fixtureBlueprint, { roleIds: ['made_up_role'] })).toBe(false);
  });
  it('refuses SVG and oversize logos, accepts PNG as pending scan', async () => {
    expect(checkLogo({ fileName: 'a.svg', mediaType: 'image/svg+xml', sizeBytes: 100 })).toBe('type');
    expect(checkLogo({ fileName: 'a.png', mediaType: 'image/png', sizeBytes: 3 * 1024 * 1024 })).toBe('size');
    const port = createFakeBrandingPort();
    const r = await port.uploadLogo({ fileName: 'a.png', mediaType: 'image/png', sizeBytes: 100 });
    expect(r.ok && r.logo.status).toBe('pending_scan');
    expect((await port.uploadLogo({ fileName: 'a.svg', mediaType: 'image/svg+xml', sizeBytes: 1 })).ok).toBe(false);
  });
  it('save goes through the port', async () => {
    const port = createFakeBrandingPort();
    expect(await port.save({ primary: S.teal, logo: null })).toEqual({ ok: true });
    expect(port.saved).toHaveLength(1);
    expect((await port.load()).primary).toBe(S.teal);
  });
});

const never = <T,>() => new Promise<T>(() => {});
const settings = (primary: string): BrandingSettings => ({ primary, logo: null });
const portOf = (over: Partial<BrandingPort>): BrandingPort => ({ ...createFakeBrandingPort(), ...over });

describe('branding review fixes: rejected colour feedback', () => {
  it('a hex that fails contrast shows the failed pair, ratio and minimum (en)', () => {
    const out = view('en', S.pale);
    const t = messages.en.branding;
    expect(out).toContain(t.reject.tooLight);
    expect(out).toContain(t.result.failedTitle);
    expect(out).toContain('1.30:1');
    expect(out).toContain('4.50:1');
    expect(out).toContain(S.pale);
    expect(out).not.toContain('<table');
  });
  it('the same feedback is translated (ar)', () => {
    const out = view('ar', S.pale);
    expect(out).toContain(messages.ar.branding.result.failedTitle);
    expect(out).toContain(messages.ar.branding.reject.tooLight);
    expect(out).not.toContain(messages.en.branding.result.failedTitle);
  });
  it('shows no pair list for text that is not a hex', () => {
    expect(view('en', 'zzz')).not.toContain(messages.en.branding.result.failedTitle);
  });
});

describe('branding review fixes: nothing is editable until load succeeds', () => {
  const editor = () =>
    renderToString(
      <NextIntlClientProvider locale="en" messages={messages.en}>
        <BrandingEditor port={createFakeBrandingPort()} initial={null} />
      </NextIntlClientProvider>,
    );
  it('colour picker, hex field, logo input and Save are all disabled while loading', () => {
    const out = editor();
    const inputs = out.match(/<input[^>]*>/g) ?? [];
    expect(inputs).toHaveLength(3);
    for (const i of inputs) expect(i).toContain('disabled');
    expect(out).toMatch(/<button[^>]*disabled/);
  });
  it('are enabled once the settings are given', () => {
    const inputs = view('en', S.teal).match(/<input[^>]*>/g) ?? [];
    for (const i of inputs) expect(i).not.toContain('disabled');
  });
  it('a late load cannot overwrite an edit, because edits are refused until the load lands', async () => {
    let finish!: (s: BrandingSettings) => void;
    const c = createBrandingController(portOf({ load: () => new Promise((r) => (finish = r)) }), null);
    c.attach();
    c.setText(S.shortNorm);
    expect(c.get().text).not.toBe(S.shortNorm);
    await c.save(S.shortNorm);
    expect(c.get().status).toBe('idle');
    finish(settings(S.teal));
    await Promise.resolve();
    expect(c.get()).toMatchObject({ loaded: 'ready', text: S.teal });
    c.setText(S.grey);
    expect(c.get().text).toBe(S.grey);
  });
  it('a failed load keeps everything locked', async () => {
    const c = createBrandingController(portOf({ load: () => Promise.reject(new Error('x')) }), null);
    c.attach();
    await Promise.resolve();
    await Promise.resolve();
    expect(c.get().loaded).toBe('failed');
    c.setText(S.teal);
    expect(c.get().text).not.toBe(S.teal);
  });
});

describe('branding review fixes: workspace switch', () => {
  it('a result that arrives after the editor is detached is ignored (load, save, logo)', async () => {
    let load!: (s: BrandingSettings) => void;
    let save!: (r: { ok: true }) => void;
    const port = portOf({ load: () => new Promise((r) => (load = r)), save: () => new Promise((r) => (save = r)) });
    const old = createBrandingController(port, null);
    const detach = old.attach();
    detach(); // tenant changed
    load(settings(S.teal));
    await Promise.resolve();
    expect(old.get()).toMatchObject({ loaded: 'loading', text: DEFAULT_PRIMARY });

    const ready = createBrandingController(port, settings(S.grey));
    const detach2 = ready.attach();
    const pending = ready.save(S.grey);
    expect(ready.get().status).toBe('saving');
    detach2();
    save({ ok: true });
    await pending;
    expect(ready.get().status).toBe('saving');
  });
  it('a new tenant starts from its own fresh state, not the previous tenant\'s', async () => {
    const a = createBrandingController(portOf({ load: async () => settings(S.teal) }), null);
    const detach = a.attach();
    await Promise.resolve();
    await Promise.resolve();
    expect(a.get().text).toBe(S.teal);
    detach();
    const b = createBrandingController(portOf({ load: () => never<BrandingSettings>() }), null);
    b.attach();
    expect(b.get()).toMatchObject({ loaded: 'loading', text: DEFAULT_PRIMARY, logo: null, status: 'idle' });
  });
  it('the screen asks for a separate port per active workspace', () => {
    const asked: string[] = [];
    const portFor = (id: string) => (asked.push(id), createFakeBrandingPort());
    const as = (tenantId: string, roles: string[]): SessionState =>
      fixtureSession.status === 'ready' ? { ...fixtureSession, claims: { ...fixtureSession.claims, tenantId, roles } } : fixtureSession;
    for (const tenantId of ['tenant-fixture-a', 'tenant-fixture-b']) {
      renderToString(
        <NextIntlClientProvider locale="en" messages={messages.en}>
          <SessionProvider initial={as(tenantId, ['owner'])}>
            <BrandingScreen portFor={portFor} />
          </SessionProvider>
        </NextIntlClientProvider>,
      );
    }
    expect(asked).toEqual(['tenant-fixture-a', 'tenant-fixture-b']);
  });
});
