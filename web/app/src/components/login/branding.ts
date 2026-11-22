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
const SAFE_VALUE = /^[#0-9a-zA-Z,.() ]{1,32}$/;
const FORBIDDEN_VALUE = /url|expr|import|var|calc|env|attr/i;
const MAX_NAME = 80;

export const isTenantKey = (v: unknown): v is string => typeof v === 'string' && SLUG.test(v);

export function safeTokens(map: unknown): TokenMap {
  const out: TokenMap = {};
  if (!map || typeof map !== 'object') return out;
  for (const name of OVERRIDABLE_TOKENS) {
    const v = (map as Record<string, unknown>)[name];
    if (typeof v === 'string' && SAFE_VALUE.test(v) && !FORBIDDEN_VALUE.test(v)) out[name] = v;
  }
  return out;
}

/** https or a same-origin path; never data:, javascript:, protocol-relative or a backslash. */
export function safeLogoUrl(v: unknown): string | null {
  if (typeof v !== 'string' || v.length > 512 || /[\s\\"'<>]/.test(v)) return null;
  if (v.startsWith('/') && !v.startsWith('//')) return v;
  try {
    return new URL(v).protocol === 'https:' ? v : null;
  } catch {
    return null;
  }
}

/** Strips control and bidi-override characters, trims and caps the length. */
export function cleanText(v: unknown): string | null {
  if (typeof v !== 'string') return null;
  // eslint-disable-next-line no-control-regex
  const s = v.replace(/[\u0000-\u001F\u007F\u200B-\u200F\u202A-\u202E\u2066-\u2069\uFEFF]/g, '').trim();
  return s ? s.slice(0, MAX_NAME) : null;
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
  const onLight = safeLogoUrl(raw.logo?.onLight);
  const onDark = safeLogoUrl(raw.logo?.onDark);
  return {
    slug: raw.slug,
    displayName: { ar: cleanText(raw.displayName?.ar) ?? undefined, en: cleanText(raw.displayName?.en) ?? undefined },
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
 * explicit dark. The input must already be sanitised.
 */
export function brandingCss(b: TenantBranding): string {
  const sel = `[data-tenant="${b.slug}"]`;
  return [
    `${sel} {\n${decls(b.light, '  ')}\n}`,
    `@media (prefers-color-scheme: dark) {\n  :root:not([data-theme="light"]) ${sel} {\n${decls(b.dark, '    ')}\n  }\n}`,
    `:root[data-theme="dark"] ${sel} {\n${decls(b.dark, '  ')}\n}`,
  ].join('\n');
}
