// QA-014 A-12: WCAG 2.x contrast of the colour pairs used in web/app CSS modules, in light and dark.
// Reads the web token copy (read only). Colours are resolved with sRGB alpha blending, matching color-mix(in srgb, ...).
// WCAG 2.2 SC 1.4.3 (4.5:1 text, 3:1 large text) and SC 1.4.11 (3:1 UI borders, focus rings, graphics). Accessed 2026-11-21.
// https://www.w3.org/TR/WCAG22/#contrast-minimum  https://www.w3.org/TR/WCAG22/#non-text-contrast
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', 'app', 'src');

export function readThemes(css) {
  const grab = (re) => {
    const m = css.match(re);
    if (!m) throw new Error(`token block not found: ${re}`);
    return Object.fromEntries([...m[1].matchAll(/--(color-[a-z]+):\s*(#[0-9a-fA-F]{6})/g)].map((x) => [x[1], x[2]]));
  };
  return {
    light: grab(/:root\s*\{([^}]*)\}/),
    dark: grab(/:root\[data-theme="dark"\]\s*\{([^}]*)\}/),
  };
}

const rgb = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
export const mix = (fg, a, bg) => { // fg at alpha a over bg, hex out
  const f = rgb(fg), b = rgb(bg);
  return `#${f.map((c, i) => Math.round(c * a + b[i] * (1 - a)).toString(16).padStart(2, '0')).join('')}`;
};
const lum = (h) => {
  const [r, g, b] = rgb(h).map((c) => { const x = c / 255; return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4; });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};
export const ratio = (a, b) => {
  const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
};

const N = 4.5, UI = 3;

// Compact table: fg and bg are functions of the theme tokens c (keys without the 'color-' prefix).
const P = [];
const add = (id, label, file, snippet, fg, bg, min) => P.push({ id, label, file, snippet, fg, bg, min });
const S = (c) => c.surface, B = (c) => c.background;
const dimOn = (p, base) => (c) => mix(c.text, p, base(c));
for (const [bn, base] of [['surface', S], ['background', B]]) {
  add(`text/${bn}`, `text on ${bn}`, 'ui/Card.module.css', 'color: var(--color-text)', (c) => c.text, base, N);
  add(`secondary70/${bn}`, `text 70% on ${bn} (helper, meta, placeholder)`, 'ui/Field.module.css', 'var(--color-text) 70%', dimOn(0.7, base), base, N);
  add(`secondary75/${bn}`, `text 75% on ${bn} (factory, console)`, 'components/factory/Factory.module.css', 'var(--color-text) 75%', dimOn(0.75, base), base, N);
  add(`primary-link/${bn}`, `primary text on ${bn} (links)`, 'components/auth/Auth.module.css', 'color: var(--color-primary)', (c) => c.primary, base, N);
  add(`danger/${bn}`, `danger text on ${bn}`, 'ui/Field.module.css', 'color: var(--color-danger)', (c) => c.danger, base, N);
  add(`focus-primary/${bn}`, `focus ring (primary) on ${bn}`, 'ui/control.module.css', 'solid var(--color-primary)', (c) => c.primary, base, UI);
  add(`focus-danger/${bn}`, `focus ring (danger) on ${bn}`, 'ui/Checkbox.module.css', 'solid var(--color-danger)', (c) => c.danger, base, UI);
  add(`border50/${bn}`, `control border (text 50%) on ${bn}`, 'ui/control.module.css', 'var(--color-text) 50%', dimOn(0.5, base), base, UI);
}
add('navHeading/surface', 'nav heading (opacity .75) on surface', 'components/shell/Shell.module.css', 'opacity: 0.75', dimOn(0.75, S), S, N);
add('onboarding-progress/background', 'onboarding progress (opacity .75) on background', 'components/onboarding/Onboarding.module.css', 'opacity: 0.75', dimOn(0.75, B), B, N);
add('on-primary', 'background on primary (button, user bubble, skip link, badge)', 'ui/Button.module.css', 'color: var(--color-background)', (c) => c.background, (c) => c.primary, N);
add('on-danger', 'background on danger button', 'ui/Button.module.css', 'color: var(--color-background)', (c) => c.background, (c) => c.danger, N);
add('on-primary-hover', 'background on primary hover (88% primary, 12% text)', 'ui/Button.module.css', 'var(--color-primary) 88%', (c) => c.background, (c) => mix(c.primary, 0.88, c.text), N);
add('on-primary-active', 'background on primary active (76% primary, 24% text)', 'ui/Button.module.css', 'var(--color-primary) 76%', (c) => c.background, (c) => mix(c.primary, 0.76, c.text), N);
add('on-danger-hover', 'background on danger hover', 'ui/Button.module.css', 'var(--color-danger) 88%', (c) => c.background, (c) => mix(c.danger, 0.88, c.text), N);
add('on-danger-active', 'background on danger active', 'ui/Button.module.css', 'var(--color-danger) 76%', (c) => c.background, (c) => mix(c.danger, 0.76, c.text), N);
add('ghost-hover', 'primary ghost text on 20% primary tint (active) over background', 'ui/Button.module.css', 'var(--color-primary) 20%', (c) => c.primary, (c) => mix(c.primary, 0.2, c.background), N);
add('ghost-hover-surface', 'primary ghost text on 20% primary tint over surface', 'ui/Button.module.css', 'var(--color-primary) 20%', (c) => c.primary, (c) => mix(c.primary, 0.2, c.surface), N);
add('secondary-hover', 'text on secondary button active (84% surface, 16% text)', 'ui/Button.module.css', 'var(--color-surface) 84%', (c) => c.text, (c) => mix(c.surface, 0.84, c.text), N);
add('nav-active', 'primary on nav link tint (14% primary) over surface', 'components/shell/Shell.module.css', 'var(--color-primary) 14%', (c) => c.primary, (c) => mix(c.primary, 0.14, c.surface), N);
add('system-bubble', 'system bubble: text 70% on text 8% over surface', 'components/chat/Chat.module.css', 'var(--color-text) 8%', (c) => mix(c.text, 0.7, mix(c.text, 0.08, c.surface)), (c) => mix(c.text, 0.08, c.surface), N);
for (const tone of ['primary', 'success', 'warning', 'danger']) {
  add(`alert-text/${tone}`, `alert text on ${tone} tint over surface`, 'ui/Alert.module.css', 'color: var(--color-text)', (c) => c.text, (c) => mix(c[tone], 0.14, c.surface), N);
  add(`alert-icon/${tone}`, `alert icon (${tone}) on its tint over surface`, 'ui/Alert.module.css', 'color: var(--alert-tone)', (c) => c[tone], (c) => mix(c[tone], 0.14, c.surface), UI);
  add(`alert-border/${tone}`, `alert border (${tone}) on surface`, 'ui/Alert.module.css', 'border: 1px solid var(--alert-tone)', (c) => c[tone], S, UI);
  add(`badge-icon/${tone}`, `badge icon (${tone}) on its tint over surface`, 'ui/Badge.module.css', 'color: var(--badge-tone)', (c) => c[tone], (c) => mix(c[tone], 0.14, c.surface), UI);
  add(`badge-text/${tone}`, `badge text on ${tone} tint over surface`, 'ui/Badge.module.css', 'color: var(--color-text)', (c) => c.text, (c) => mix(c[tone], 0.14, c.surface), N);
}
add('blueprint-node-stroke', 'flow node stroke (text 50%) on surface', 'components/blueprint/Blueprint.module.css', 'var(--color-text) 50%', dimOn(0.5, S), S, UI);
add('blueprint-edge', 'flow edge (text 60%) on background', 'components/blueprint/Blueprint.module.css', 'var(--color-text) 60%', dimOn(0.6, B), B, UI);
add('blueprint-badge-text', 'flow step number (background) on primary', 'components/blueprint/Blueprint.module.css', 'fill: var(--color-background)', (c) => c.background, (c) => c.primary, N);

export const PAIRS_ALL = P;

export function evaluate(themes) {
  const out = [];
  for (const mode of ['light', 'dark']) {
    const c = Object.fromEntries(Object.entries(themes[mode]).map(([k, v]) => [k.replace('color-', ''), v]));
    for (const p of P) out.push({ ...p, mode, ratio: ratio(p.fg(c), p.bg(c)) });
  }
  return out;
}

export const tokenCss = () => fs.readFileSync(path.join(root, 'styles', 'tokens.generated.css'), 'utf8');
export const readSource = (file) => fs.readFileSync(path.join(root, file), 'utf8');

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  for (const r of evaluate(readThemes(tokenCss()))) if (r.ratio < r.min) console.log(`${r.mode} ${r.id} ${r.ratio.toFixed(2)} < ${r.min}`);
}
