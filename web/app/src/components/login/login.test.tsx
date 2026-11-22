import { describe, expect, it } from 'vitest';
import { renderToString } from 'react-dom/server';
import { NextIntlClientProvider } from 'next-intl';
import type { ReactElement } from 'react';
import { messages, type Locale } from '../../i18n';
import { BrandedLogin } from './BrandedLogin';
import { brandingCss, safeLogoUrl, safeTokens, sanitiseBranding, type TenantBranding } from './branding';
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
const withDark: TenantBranding = { ...sample, logo: { onLight: '/a.svg', onDark: 'https://assets.example.test/b.svg' } };

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
    expect(out).toContain('https://assets.example.test/b.svg');
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
    expect(safeLogoUrl('https://assets.example.test/l.svg')).not.toBeNull();
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
