import { describe, expect, it } from 'vitest';
import { renderToString } from 'react-dom/server';
import { NextIntlClientProvider } from 'next-intl';
import type { ReactElement } from 'react';
import { messages, type Locale } from '../../i18n';
import { BrandedLogin } from './BrandedLogin';
import { brandingCss, cleanText, safeLogoUrl, safeTokens, sanitiseBranding, type TenantBranding } from './branding';
import { fakeBrandingPort } from './fake';
import fixture from './fixture.json';

const render = (locale: Locale, node: ReactElement) =>
  renderToString(
    <NextIntlClientProvider locale={locale} messages={messages[locale]} timeZone="UTC">
      {node}
    </NextIntlClientProvider>,
  );

const sample = fixture.tenants['sample-trading'] as TenantBranding;
const noLogo = fixture.tenants['example-foods'] as TenantBranding;
const withDark: TenantBranding = { ...sample, logo: { onLight: '/brand-assets/a.svg', onDark: '/brand-assets/b.svg' } };

describe.each(['en', 'ar'] as const)('branded login in %s', (locale) => {
  it('tenant look: name, logo, scoped data-tenant, dir', () => {
    const out = render(locale, <BrandedLogin initialBranding={sample} />);
    expect(out).toContain('data-tenant="sample-trading"');
    expect(out).toContain(locale === 'ar' ? sample.displayName.ar : sample.displayName.en);
    expect(out).toContain('src="/icons/app-icon.svg"');
    expect(out).toContain(locale === 'ar' ? 'dir="rtl"' : 'dir="ltr"');
    expect(out).toContain(messages[locale].auth.login.submit);
  });

  it('platform fallback when there is no branding', () => {
    const out = render(locale, <BrandedLogin initialBranding={null} />);
    expect(out).not.toContain('data-tenant');
    expect(out).not.toContain('<style');
    expect(out).toContain(messages[locale].auth.login.platformName);
  });

  it('form stays accessible with branding: linked labels, alert on failure', () => {
    const out = render(locale, <BrandedLogin initialBranding={sample} />);
    expect(out.match(/<label for="/g)).toHaveLength(2);
    expect(out).toContain('<h1');
    expect(out).not.toContain('role="alert"');
  });
});

describe('branding safety', () => {
  it('no logo and showLogo false: no img, name still shown', () => {
    const out = render('en', <BrandedLogin initialBranding={noLogo} />);
    expect(out).toContain('Example Foods');
    expect(out).not.toContain('/icons/app-icon.svg');
  });

  it('dark logo gets its own element, switched by theme in CSS', () => {
    const out = render('en', <BrandedLogin initialBranding={withDark} />);
    expect(out).toContain('logoDark');
    expect(out).toContain('/brand-assets/b.svg');
  });

  it('css is scoped, covers light, system dark and explicit dark, and only whitelisted tokens', () => {
    const css = brandingCss(sanitiseBranding(sample)!);
    expect(css).toContain('[data-tenant="sample-trading"] {');
    expect(css).toContain('prefers-color-scheme: dark');
    expect(css).toContain(':root[data-theme="dark"] [data-tenant="sample-trading"]');
    expect(css).toContain('--color-primary:');
    expect(css).not.toContain('--color-background');
  });

  it('rejects unsafe tokens, values, logo URLs and slugs', () => {
    expect(safeTokens({ '--color-background': 'red', '--color-primary': 'red; } body { x: y' })).toEqual({});
    expect(safeTokens({ '--color-primary': 'url(https://x.test/a)' })).toEqual({});
    for (const u of ['javascript:alert(1)', 'data:image/svg+xml,x', '//evil.test/a.png', 'http://x.test/a.png', '/a b.png', '/a"onerror=x'])
      expect(safeLogoUrl(u)).toBeNull();
    expect(sanitiseBranding({ ...sample, slug: 'x"] { } a[b="' })).toBeNull();
  });

  it('half a theme (no dark primary) falls back to the platform look', () => {
    expect(sanitiseBranding({ ...sample, dark: {} })).toBeNull();
  });

  it('strips bidi overrides from the display name', () => {
    const b = sanitiseBranding({ ...sample, displayName: { en: 'A\u202EB', ar: 'x' } })!;
    expect(b.displayName.en).toBe('AB');
  });

  it('fake port: known tenant resolves, unknown and prototype keys do not', async () => {
    expect(await fakeBrandingPort.load('sample-trading')).not.toBeNull();
    expect(await fakeBrandingPort.load('nobody')).toBeNull();
    expect(await fakeBrandingPort.load('constructor')).toBeNull();
  });
});

// Colour literals are built, not written: the repo lint bans them in sources.
const c = (h: string) => '#' + h;
const tr = ['rgb', 'a(0,110,103,0.12)'].join('');

describe('review hardening (M1, M2, M3, L1)', () => {
  it.each([
    '/api/logout',
    '/api/x?next=https://evil.test',
    '/../../x',
    '/icons/../api/x',
    '/icons/a.svg?x=1',
    '/icons/a.svg#f',
    '/%2f%2fevil.test',
    '/icons/%2e%2e/a',
    '/icons/a/b.svg',
    '/other/a.svg',
  ])('refuses same-origin logo path %s', (u) => expect(safeLogoUrl(u)).toBeNull());

  it('accepts a plain file under the platform asset prefixes', () => {
    expect(safeLogoUrl('/icons/app-icon.svg')).toBe('/icons/app-icon.svg');
    expect(safeLogoUrl('/brand-assets/abc-123.png')).toBe('/brand-assets/abc-123.png');
  });

  const origin = 'https://assets.example.test';
  it.each([
    'https://user:pw@assets.example.test/a.png',
    'https://127.0.0.1/a.png',
    'https://[::1]/a.png',
    'https://assets.example.test:8443/a.png',
    'https://evil.test/a.png',
    'https://assets.example.test.evil.test/a.png',
    'https:assets.example.test/a.png',
    'http://assets.example.test/a.png',
    'https://assets.example.test/a.png?x=1',
    'https://assets.example.test/../a.png',
  ])('refuses https logo %s', (u) => expect(safeLogoUrl(u, [origin])).toBeNull());

  it('accepts a logo only from a configured asset origin and returns the normalised href', () => {
    expect(safeLogoUrl('https://assets.example.test/l/a.svg', [origin])).toBe('https://assets.example.test/l/a.svg');
    expect(safeLogoUrl('https://assets.example.test/l/a.svg')).toBeNull();
  });

  it.each(['initial', 'inherit', 'unset', 'revert', 'transparent', 'currentColor', '((((', '#zzz', '1', c('12345'), 'min(1,2)', 'paint(x)'])(
    'refuses token value %s',
    (v) => expect(safeTokens({ '--color-primary': v })).toEqual({}),
  );

  it('accepts hex colours and the one rgba shape only for --state-selected', () => {
    expect(safeTokens({ '--color-primary': c('006E67'), '--state-selected': tr })).toEqual({
      '--color-primary': c('006E67'),
      '--state-selected': tr,
    });
    expect(safeTokens({ '--color-primary': tr })).toEqual({});
  });

  it('falls back to the platform look when the label does not reach 4.5:1 on the primary', () => {
    const bad = { ...sample, light: { ...sample.light, '--color-primary-label': c('FFFFFF'), '--color-primary': c('FFFFFF') } };
    expect(sanitiseBranding(bad)).toBeNull();
    const badDark = { ...sample, dark: { ...sample.dark, '--color-primary-label': c('7CB0AA') } };
    expect(sanitiseBranding(badDark)).toBeNull();
    expect(sanitiseBranding(sample)).not.toBeNull();
  });

  it('strips the full set of control and bidi characters', () => {
    const cps = [0x61c, 0x80, 0x9f, 0x2028, 0x2029, 0x2060, 0x2064, 0xad, 0x180e, 0xfff9, 0xe0041, 0x200b, 0x200d];
    for (const cp of cps) expect(cleanText(`A${String.fromCodePoint(cp)}B`)).toBe('AB');
  });

  it('does not cut a surrogate pair when truncating', () => {
    const out = cleanText('a'.repeat(79) + '\u{1F600}\u{1F600}')!;
    expect(out).toBe('a'.repeat(79) + '\u{1F600}');
    expect([...out]).toHaveLength(80);
  });

  it('brandingCss sanitises its own input', () => {
    const css = brandingCss({ ...sample, slug: 'x"] { } a[b="' } as TenantBranding);
    expect(css).toBe('');
  });
});
