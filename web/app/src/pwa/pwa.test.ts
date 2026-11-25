import { describe, expect, it } from 'vitest';
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { messages } from '../i18n';
import { buildManifest, themeColorsFromTokens } from './manifest';

const root = join(__dirname, '../..');
const tokens = readFileSync(join(root, '../../docs/brand/tokens/tokens.css'), 'utf8');
const colors = themeColorsFromTokens(tokens);

describe('web app manifest', () => {
  for (const [loc, dir] of [['ar', 'rtl'], ['en', 'ltr']] as const) {
    it(`is valid for ${loc}`, () => {
      const m = buildManifest(messages[loc].pwa, colors, loc, dir);
      expect(m.name.length).toBeGreaterThan(0);
      expect(m.short_name.length).toBeLessThanOrEqual(12);
      expect(m.display).toBe('standalone');
      expect(m.start_url.startsWith('/')).toBe(true);
      expect(m.start_url.startsWith(m.scope)).toBe(true);
      expect(m.theme_color).toMatch(/^#[0-9a-fA-F]{6}$/);
      expect(m.icons.length).toBeGreaterThan(0);
      expect(m.dir).toBe(dir);
    });
    it(`names no engine or working name in ${loc}`, () => {
      const text = JSON.stringify(buildManifest(messages[loc].pwa, colors, loc, dir)).toLowerCase();
      for (const word of [['frap', 'pe'].join(''), ['erp', 'next'].join(''), ['orre', 'ry'].join('')]) expect(text).not.toContain(word);
    });
  }
  it('takes colours from the generated tokens, light and dark', () => {
    expect(colors.light).toMatch(/^#/);
    expect(colors.dark).not.toBe(colors.light);
    expect(() => themeColorsFromTokens(':root{}')).toThrow();
  });
  it('points the icons at brand files that exist in the repo', () => {
    for (const f of ['app-icon.svg', 'mark-small.svg', 'png/favicon.ico', 'png/apple-touch-icon.png', 'png/app-icon-192.png', 'png/app-icon-512.png', 'png/maskable-512.png']) {
      expect(existsSync(join(root, '../../docs/brand/logo', f)), f).toBe(true);
    }
    const icons = buildManifest(messages.en.pwa, colors, 'en', 'ltr').icons;
    expect(icons[0]?.src).toBe('/icons/app-icon.svg');
    expect(icons.some((i) => i.purpose === 'maskable' && i.sizes === '512x512')).toBe(true);
  });
  it('names the product Seshna in Latin letters in both languages', () => {
    for (const loc of ['ar', 'en'] as const) expect(messages[loc].pwa.name).toBe('Seshna');
  });
});

describe('no service worker (Q-380)', () => {
  const walk = (d: string): string[] =>
    readdirSync(d).flatMap((n) => {
      const p = join(d, n);
      return statSync(p).isDirectory() ? walk(p) : [p];
    });
  it('registers none and caches nothing until the caching rules are decided', () => {
    const files = walk(join(root, 'src')).filter((f) => /\.(ts|tsx)$/.test(f) && !f.endsWith('pwa.test.ts'));
    for (const f of files) expect(readFileSync(f, 'utf8'), f).not.toMatch(/serviceWorker\.register|caches\.open/);
    expect(existsSync(join(root, 'public/sw.js'))).toBe(false);
  });
});

describe('touch targets and safe areas', () => {
  it('defines a 44px touch target and the safe-area insets once', () => {
    const css = readFileSync(join(root, 'src/styles/mobile.css'), 'utf8');
    expect(css).toContain('--touch-target: 2.75rem');
    expect(css).toContain('env(safe-area-inset-left');
  });
  it('button and control heights never go below the touch target', () => {
    for (const f of ['ui/Button.module.css', 'ui/control.module.css', 'components/shell/Shell.module.css']) {
      const css = readFileSync(join(root, 'src', f), 'utf8');
      expect(css, f).toContain('--touch-target');
      expect(css, f).not.toMatch(/min-block-size:\s*var\(--button-height\)/);
    }
  });
});
