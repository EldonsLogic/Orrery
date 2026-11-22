// WEB-007: server-render the branding screen in both languages (same approach as blueprint.test.tsx; no jsdom).
import { describe, expect, it } from 'vitest';
import { renderToString } from 'react-dom/server';
import { NextIntlClientProvider } from 'next-intl';
import data from '../../../settings/branding/colour.data.json';
import { messages } from '../../../i18n';
import { fixtureBlueprint } from '../../../blueprint/fixture';
import { canEditBranding } from '../../../settings/branding/access';
import { checkLogo, createFakeBrandingPort } from '../../../settings/branding/port';
import { BrandingEditor } from './BrandingScreen';

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
    const out = view('en', data.defaultPrimary);
    expect(out).toContain('accept="image/png,image/jpeg"');
    expect(out).not.toContain('<img');
  });
});

describe('branding access and port', () => {
  it('only owner and general manager may edit (deny by default)', () => {
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
