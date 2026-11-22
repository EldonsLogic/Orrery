/**
 * Tenant branding for the login page (WEB-008). Data in, CSS text out; nothing here reads the
 * browser. The resolved values come from the branding derivation (docs/brand/tools/derive_tenant_theme.py,
 * served per docs/architecture/theming.md) and are untrusted on arrival: slug, token names, values and
 * the logo URL are all checked before they reach CSS or an img tag. Only the tenant-overridable
 * tokens may be set; background, surface, text and status colours never are (ADR-0014).
 */
import type { Locale } from '../../i18n';

export type LocalizedText = Partial<Record<Locale, string>>;
export type TokenMap = Record<string, string>;

export type TenantBranding = {
  slug: string;
  displayName: LocalizedText;
  headline?: LocalizedText;
  /** Logo URLs (https or same-origin path). A missing dark logo reuses the light one. */
  logo?: { onLight: string; onDark?: string };
  showLogo?: boolean;
  light: TokenMap;
  dark: TokenMap;
};

/** Pre-sign-in, so no session: the port gets only the tenant key from the address. */
export interface TenantBrandingPort {
  load(tenantKey: string): Promise<TenantBranding | null>;
}

export const OVERRIDABLE_TOKENS = [
  '--color-primary',
  '--color-primary-hover',
  '--color-primary-pressed',
  '--color-primary-label',
  '--color-link-visited',
  '--state-selected',
] as const;

const SLUG = /^[a-z0-9][a-z0-9-]{0,62}$/;
const HEX = /^#(?:[0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})$/;
// The one translucent shape the derivation emits (--state-selected): three channels and an alpha.
const TRANSLUCENT = /^rgb[a]\((?:\d{1,3},){3}(?:0|1|0?\.\d{1,3})\)$/;
const MAX_NAME = 80;
/** Fixed platform asset paths (copied at build or served by the asset pipeline): one plain file name, no query. */
const ASSET_PATH = /^\/(?:icons|brand-assets)\/[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;

/** Configured platform asset origins (theming.md: separate asset origin). None configured: https logos are refused. */
export function configuredAssetOrigins(): string[] {
  return (process.env.NEXT_PUBLIC_ASSET_ORIGIN ?? '')
    .split(',')
    .map((o) => o.trim())
    .filter((o) => /^https:\/\/[a-z0-9.-]+$/.test(o));
}

export const isTenantKey = (v: unknown): v is string => typeof v === 'string' && SLUG.test(v);

function channels(hex: string): [number, number, number] {
  const h = hex.length === 4 ? [...hex.slice(1)].map((c) => c + c).join('') : hex.slice(1);
  return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16)) as [number, number, number];
}

function luminance(hex: string): number {
  const [r, g, b] = channels(hex).map((v) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  }) as [number, number, number];
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function contrastRatio(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (hi + 0.05) / (lo + 0.05);
}

/** Only colours: hex everywhere, the derived translucent shape for --state-selected. Nothing else reaches CSS. */
export function safeTokens(map: unknown): TokenMap {
  const out: TokenMap = {};
  if (!map || typeof map !== 'object') return out;
  for (const name of OVERRIDABLE_TOKENS) {
    const v = (map as Record<string, unknown>)[name];
    if (typeof v !== 'string') continue;
    if (HEX.test(v) || (name === '--state-selected' && TRANSLUCENT.test(v))) out[name] = v;
  }
  return out;
}

/** Same-origin: a plain file under a platform asset prefix. https: only from a configured asset origin. */
export function safeLogoUrl(v: unknown, origins: string[] = configuredAssetOrigins()): string | null {
  if (typeof v !== 'string' || v.length > 512 || /[\s\\"'<>%?#]/.test(v)) return null;
  if (v.startsWith('/')) return ASSET_PATH.test(v) && !v.includes('..') ? v : null;
  let u: URL;
  try {
    u = new URL(v);
  } catch {
    return null;
  }
  const ok = u.protocol === 'https:' && !u.username && !u.password && !u.port && !u.search && !u.hash && origins.includes(u.origin);
  if (!ok || u.pathname.split('/').some((seg) => seg === '..' || seg === '.')) return null;
  return u.href === v ? u.href : null;
}

/** Strips control and bidi-override characters, trims and caps the length. */
function hostile(cp: number): boolean {
  return (
    cp <= 0x1f ||
    (cp >= 0x7f && cp <= 0x9f) ||
    cp === 0xad ||
    cp === 0x61c ||
    cp === 0x180e ||
    (cp >= 0x200b && cp <= 0x200f) ||
    (cp >= 0x2028 && cp <= 0x202e) ||
    (cp >= 0x2060 && cp <= 0x206f) ||
    cp === 0xfeff ||
    (cp >= 0xfff9 && cp <= 0xfffb) ||
    (cp >= 0xe0000 && cp <= 0xe007f)
  );
}

/** Strips control, format and bidi characters, trims and caps the length by code points. */
export function cleanText(v: unknown): string | null {
  if (typeof v !== 'string') return null;
  const s = [...v].filter((c) => !hostile(c.codePointAt(0)!)).join('').trim();
  return s ? [...s].slice(0, MAX_NAME).join('') : null;
}

export function pickText(t: LocalizedText | undefined, locale: Locale): string | null {
  return cleanText(t?.[locale]) ?? cleanText(t?.[locale === 'ar' ? 'en' : 'ar']);
}

/** Returns a branding that is safe to render, or null (platform look) when it is unusable. */
export function sanitiseBranding(raw: TenantBranding | null | undefined): TenantBranding | null {
  if (!raw || !isTenantKey(raw.slug)) return null;
  const light = safeTokens(raw.light);
  const dark = safeTokens(raw.dark);
  // The derivation always yields both themes; half a theme would break contrast, so fall back.
  if (!light['--color-primary'] || !dark['--color-primary'] || !light['--color-primary-label'] || !dark['--color-primary-label']) return null;
  for (const m of [light, dark]) {
    const label = m['--color-primary-label'];
    if (!label || !HEX.test(label)) return null;
    for (const k of ['--color-primary', '--color-primary-hover', '--color-primary-pressed'])
      if (m[k] && HEX.test(m[k]) && contrastRatio(label, m[k]) < 4.5) return null;
  }
  const name = { ar: cleanText(raw.displayName?.ar), en: cleanText(raw.displayName?.en) };
  if (!name.ar && !name.en) return null; // a brand with no name would be silent for screen readers
  const onLight = safeLogoUrl(raw.logo?.onLight);
  const onDark = safeLogoUrl(raw.logo?.onDark);
  return {
    slug: raw.slug,
    displayName: { ar: name.ar ?? undefined, en: name.en ?? undefined },
    headline: { ar: cleanText(raw.headline?.ar) ?? undefined, en: cleanText(raw.headline?.en) ?? undefined },
    logo: onLight ? { onLight, onDark: onDark ?? undefined } : undefined,
    showLogo: raw.showLogo !== false,
    light,
    dark,
  };
}

const decls = (m: TokenMap, indent: string) =>
  Object.entries(m)
    .map(([k, v]) => `${indent}${k}: ${v};`)
    .join('\n');

/**
 * Scoped to the login root (`[data-tenant]`), same three cases as tokens.css: light, system dark,
 * explicit dark. Sanitises its input itself; unusable branding gives ''.
 */
export function brandingCss(input: TenantBranding): string {
  const b = sanitiseBranding(input);
  if (!b) return '';
  const sel = `[data-tenant="${b.slug}"]`;
  return [
    `${sel} {\n${decls(b.light, '  ')}\n}`,
    `@media (prefers-color-scheme: dark) {\n  :root:not([data-theme="light"]) ${sel} {\n${decls(b.dark, '    ')}\n  }\n}`,
    `:root[data-theme="dark"] ${sel} {\n${decls(b.dark, '  ')}\n}`,
  ].join('\n');
}
