/**
 * Tenant primary-colour derivation and contrast check (WEB-007). TypeScript port of the PRIMARY-colour
 * path of docs/brand/tools/derive_tenant_theme.py and themelib.py (BRD-006): same constants, same
 * search, same pairs. Parity is enforced by colour.test.ts, which runs the Python tool on sample
 * colours. Not ported: the optional accent and the status-closeness warnings (the screen offers
 * neither). Pure, no DOM, no network.
 */
import data from './colour.data.json';
import tokens from './colour.tokens.generated.json';

export type Mode = 'light' | 'dark';

// Base colours of docs/brand/tokens/tokens.json, generated (scripts/gen-branding-colours.mjs; never edit the JSON by hand).
export const BASE = tokens.base;
/** Brand Cobalt, the platform default primary; also the neutral start of the picker. */
export const DEFAULT_PRIMARY: string = tokens.defaultPrimary;
const WHITE: string = data.white;
const CARBON_DEEP: string = data.carbonDeep;
const CARBON_INK: string = data.carbonInk;

const LIGHT_MAX_SHIFT = 0.2;
const MIN_CHROMA = 0.04;
const MIN_TEXT_CONTRAST = 1.5;
const DANGER_DE = 0.1;
const DARK_L0 = 0.72;
const DARK_CHROMA = 0.65;
const STEP = 0.005;

const P = {
  light: { raisedMix: 0, hover: 0.06, pressed: 0.12, selected: 0.12, pHover: [CARBON_INK, 0.12], pPressed: [CARBON_INK, 0.24], visited: 0.45 },
  dark: { raisedMix: 0.05, hover: 0.06, pressed: 0.12, selected: 0.16, pHover: [WHITE, 0.12], pPressed: [CARBON_DEEP, 0.12], visited: 0.45 },
} as const;
const SECONDARY_HOVER = 0.08;
const SECONDARY_PRESSED = 0.14;

// ---- sRGB, contrast (WCAG 2.x) ----
const channels = (h: string): number[] => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
// Python round() is half-to-even (int(round(v)) in themelib), so exact .5 must match it.
const roundEven = (v: number) => (Math.abs(v % 1) === 0.5 ? 2 * Math.round(v / 2) : Math.round(v));
const hex = (c: number[]): string => '#' + c.map((v) => Math.max(0, Math.min(255, roundEven(v))).toString(16).padStart(2, '0')).join('').toUpperCase();
const lin = (v: number) => ((v /= 255) <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
const delin = (v: number) => {
  v = Math.max(0, Math.min(1, v));
  return 255 * (v <= 0.0031308 ? 12.92 * v : 1.055 * v ** (1 / 2.4) - 0.055);
};
const lum = (h: string) => {
  const [r, g, b] = channels(h).map(lin);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};
export const ratio = (a: string, b: string): number => {
  const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
};
const mix = (a: string, b: string, t: number) => hex(channels(a).map((x, i) => x + (channels(b)[i] - x) * t));
const over = (fg: string, alpha: number, bg: string) => mix(bg, fg, alpha);

// ---- OKLab / OKLCH ----
const toOklab = (h: string): number[] => {
  const [r, g, b] = channels(h).map(lin);
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  return [0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s, 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s, 0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s];
};
const fromOklabLin = (L: number, a: number, b: number): number[] => {
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;
  return [4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s, -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s, -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s];
};
const toOklch = (h: string): [number, number, number] => {
  const [L, a, b] = toOklab(h);
  return [L, Math.hypot(a, b), ((Math.atan2(b, a) * 180) / Math.PI + 360) % 360];
};
const inGamut = (c: number[]) => c.every((v) => v >= -1e-4 && v <= 1 + 1e-4);
const oklchToHex = (L: number, C: number, H: number): string => {
  const hr = (H * Math.PI) / 180;
  const at = (c: number) => fromOklabLin(L, c * Math.cos(hr), c * Math.sin(hr));
  if (!inGamut(at(C))) {
    let lo = 0;
    let hi = C;
    for (let i = 0; i < 40; i++) {
      const mid = (lo + hi) / 2;
      if (inGamut(at(mid))) lo = mid;
      else hi = mid;
    }
    C = lo;
  }
  return hex(at(C).map(delin));
};
const dE = (a: string, b: string) => Math.hypot(...toOklab(a).map((v, i) => v - toOklab(b)[i]));

// ---- theme and pairs (primary-tagged pairs only) ----
export type Pair = { id: string; fg: string; bg: string; min: number; ratio: number; ok: boolean };
export type Theme = { primary: string; vars: Readonly<Record<string, string>>; pairs: ReadonlyArray<Pair> };

const pickLabel = (fill: string) => (ratio(WHITE, fill) >= 4.5 ? WHITE : ratio(WHITE, fill) >= ratio(CARBON_DEEP, fill) ? WHITE : CARBON_DEEP);

function build(mode: Mode, primary: string): Theme {
  const b = BASE[mode];
  const p = P[mode];
  const raised = p.raisedMix ? mix(b.surface, b.text, p.raisedMix) : b.surface;
  const hover = over(b.text, p.hover, b.surface);
  const selected = over(primary, p.selected, b.surface);
  const label = mode === 'light' ? pickLabel(primary) : ratio(CARBON_DEEP, primary) >= 4.5 ? CARBON_DEEP : WHITE;
  const pHover = mix(primary, p.pHover[0], p.pHover[1]);
  const pPressed = mix(primary, p.pPressed[0], p.pPressed[1]);
  const visited = mix(primary, b.text, p.visited);
  const S: Record<string, string> = { background: b.background, surface: b.surface, raised, hover, selected };
  const sec = (tint: number, sn: string) => over(primary, tint, S[sn]);
  const specs: Array<[string, string, string, number]> = [];
  for (const sn of ['background', 'surface', 'raised', 'hover', 'selected']) specs.push([`link/${sn}`, primary, S[sn], 4.5]);
  for (const sn of ['background', 'surface', 'raised']) specs.push([`visited/${sn}`, visited, S[sn], 4.5]);
  for (const [k, t] of [['secondary-hover', SECONDARY_HOVER], ['secondary-pressed', SECONDARY_PRESSED]] as const) {
    for (const sn of ['background', 'surface']) specs.push([`${k}/${sn}`, primary, sec(t, sn), 4.5]);
  }
  specs.push(['btn-primary', label, primary, 4.5], ['btn-primary-hover', label, pHover, 4.5], ['btn-primary-pressed', label, pPressed, 4.5]);
  for (const sn of ['background', 'surface', 'raised']) specs.push([`ring/${sn}`, primary, S[sn], 3]);
  const pairs = specs.map(([id, fg, bg, min]) => ({ id, fg, bg, min, ratio: Math.round(ratio(fg, bg) * 100) / 100, ok: ratio(fg, bg) + 1e-9 >= min }));
  const vars = {
    '--color-background': b.background, '--color-surface': b.surface, '--color-surface-raised': raised, '--color-text': b.text,
    '--color-primary': primary, '--color-primary-hover': pHover, '--color-primary-pressed': pPressed, '--color-primary-label': label,
  };
  return { primary, vars, pairs };
}

const failsPrimary = (mode: Mode, primary: string) => build(mode, primary).pairs.some((x) => !x.ok);
const frange = (a: number, b: number): number[] => {
  const n = Math.round(Math.abs(b - a) / STEP);
  return Array.from({ length: n + 1 }, (_, i) => a + (b >= a ? 1 : -1) * STEP * i);
};

export type RejectCode = 'invalid' | 'grey' | 'danger' | 'tooLight' | 'tooDark' | 'darkNoAa' | 'darkGrey' | 'internal';
export type Derived = { status: 'ok'; light: Theme; dark: Theme; adjusted: { light: boolean; dark: boolean } } | { status: 'rejected'; code: RejectCode };

export function normHex(s: string): string | null {
  let v = s.trim().replace(/^#/, '');
  if (/^[0-9a-fA-F]{3}$/.test(v)) v = [...v].map((c) => c + c).join('');
  return /^[0-9a-fA-F]{6}$/.test(v) ? '#' + v.toUpperCase() : null;
}

export function derive(input: string): Derived {
  const no = (code: RejectCode): Derived => ({ status: 'rejected', code });
  const p = normHex(input);
  if (!p) return no('invalid');
  const [L, C, H] = toOklch(p);
  if (C < MIN_CHROMA) return no('grey');
  if (dE(p, BASE.light.danger) < DANGER_DE) return no('danger');
  const lightP = [p, ...frange(L - STEP, 0.15).map((l) => oklchToHex(l, C, H))].find((h) => !failsPrimary('light', h));
  if (!lightP || (lightP !== p && L - toOklch(lightP)[0] > LIGHT_MAX_SHIFT)) return no('tooLight');
  if (ratio(lightP, BASE.light.text) < MIN_TEXT_CONTRAST) return no('tooDark');
  if (dE(lightP, BASE.light.danger) < DANGER_DE) return no('danger');
  const c0 = C * DARK_CHROMA;
  const darkP = frange(Math.max(L, DARK_L0), 0.97).map((l) => oklchToHex(l, c0, H)).find((h) => !failsPrimary('dark', h));
  if (!darkP) return no('darkNoAa');
  if (toOklch(darkP)[1] < MIN_CHROMA * 0.75 || dE(darkP, BASE.dark.danger) < DANGER_DE || dE(darkP, BASE.dark.text) < 0.08) return no('darkGrey');
  const light = build('light', lightP);
  const dark = build('dark', darkP);
  if ([...light.pairs, ...dark.pairs].some((x) => !x.ok)) return no('internal');
  return { status: 'ok', light, dark, adjusted: { light: lightP !== p, dark: true } };
}

/** What the user's colour would score as-is (before any adjustment), per mode: honest feedback on the raw pick. */
export function rawPairs(input: string): { light: ReadonlyArray<Pair>; dark: ReadonlyArray<Pair> } | null {
  const p = normHex(input);
  return p ? { light: build('light', p).pairs, dark: build('dark', p).pairs } : null;
}
