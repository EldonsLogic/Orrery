// WEB-029: the design foundation defines each role once and keeps glass to a safe, solid-by-default material.
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const read = (rel: string) => readFileSync(join(__dirname, rel), 'utf8').replace(/\/\*[\s\S]*?\*\//g, '');
const css = read('foundation.css');
const root = css.slice(0, css.indexOf('}'));
const tokens = readFileSync(join(__dirname, '../../../../docs/brand/tokens/tokens.css'), 'utf8');
const proposed = readFileSync(join(__dirname, '../../../../docs/brand/tokens/tokens.proposed.css'), 'utf8');

describe('design foundation', () => {
  it('defines every role once in :root', () => {
    const roles = [
      '--radius-md', '--radius-sm', '--radius-pill', '--hairline',
      '--text-strong-weight', '--text-label-size', '--text-label-weight', '--text-kpi-size', '--text-kpi-line', '--text-kpi-weight',
      '--text-display-fluid', '--text-h1-fluid', '--measure',
      '--control-sm', '--control-md', '--control-lg', '--icon-sm', '--icon-md', '--icon-lg', '--control-gap',
      '--page-max', '--page-pad', '--page-band', '--main-pad-block', '--glass-fill', '--glass-filter', '--glass-edge',
      '--bp-phone', '--bp-tablet', '--bp-laptop', '--bp-desktop',
    ];
    for (const r of roles) expect(root.split(`${r}:`)).toHaveLength(2);
  });
  it('builds on the token files: spacing steps, control heights, 14 px cards', () => {
    for (const s of ['--space-0_5: 4px', '--space-1: 8px', '--space-1_5: 12px', '--space-2: 16px', '--space-3: 24px', '--space-6: 48px']) expect(proposed).toContain(s);
    for (const s of ['--control-height-compact: 32px', '--control-height: 40px', '--control-height-touch: 48px']) expect(proposed).toContain(s);
    expect(tokens).toContain('--radius-card: 14px;');
    expect(tokens).toContain('--radius-control: 8px;');
  });
  it('uses only weights 400, 500, 600 and 700', () => {
    for (const m of css.matchAll(/weight:\s*(\d+)/g)) expect(['400', '500', '600', '700']).toContain(m[1]);
  });
  it('fluid type only for display and h1; body stays fixed', () => {
    expect([...css.matchAll(/(--[\w-]+):\s*clamp\(/g)].map((m) => m[1])).toEqual(['--text-display-fluid', '--text-h1-fluid']);
  });
  it('keeps glass solid unless backdrop-filter is supported, and solid again for reduced transparency', () => {
    expect(root).toContain('--glass-filter: none');
    expect(root).toContain('--glass-alpha: 100%');
    expect(css).toMatch(/@supports \(\(backdrop-filter: blur\(1px\)\) or \(-webkit-backdrop-filter: blur\(1px\)\)\)/);
    const reduced = css.slice(css.indexOf('@media (prefers-reduced-transparency: reduce), (prefers-contrast: more)'));
    expect(reduced).toContain('--glass-filter: none !important');
    expect(reduced).toContain('--glass-alpha: 100% !important');
  });
  it('has no shadows, gradients or decorative shapes', () => {
    expect(css).not.toMatch(/box-shadow|gradient\(|border-radius:\s*50%|glass-highlight/);
  });
  it('keeps muted text readable on glass: 88% fill, no per-theme alpha', () => {
    expect(css).toContain('--glass-alpha: 88%');
    expect(css.match(/--glass-alpha:/g)).toHaveLength(3); // solid default, the @supports value, the accessibility reset
  });
});

describe('shell chrome', () => {
  const shell = read('../components/shell/Shell.module.css');
  const block = (sel: string) => shell.match(new RegExp(`(?:^|\\n)${sel.replace(/[.[\]()]/g, '\\$&')} \\{([^}]*)\\}`))?.[1] ?? '';
  it('uses glass only on the top bar, side navigation and dock; popovers and panels are solid', () => {
    const withGlass = [...shell.matchAll(/(?:^|\n)([^\n{}]+) \{[^}]*backdrop-filter/g)].map((m) => m[1]);
    expect(withGlass).toEqual(['.topBar', '.navWrap', '.dock']);
    for (const sel of ['.popover', '.panel']) expect(block(sel)).toContain('background: var(--color-surface)');
  });
  it('has no decorative shadow: only the overlay token on popovers', () => {
    expect(shell).not.toContain('glass-highlight');
    expect([...shell.matchAll(/box-shadow:\s*([^;]+);/g)].map((m) => m[1])).toEqual(['var(--shadow-overlay)', 'var(--shadow-overlay)']);
  });
  it('derives the nav offset from the same height as the top bar', () => {
    expect(shell).not.toContain('--topbar-height');
    expect(block('.topBar')).toContain('min-block-size: var(--shell-bar-height)');
    expect(block('.navInner')).toContain('var(--shell-bar-height)');
  });
  it('keeps both languages reachable on phones and a 44px touch target', () => {
    expect(shell).not.toMatch(/langButton\[aria-pressed='true'\]\s*\{\s*display:\s*none/);
    expect(shell).toContain('min-block-size: calc(var(--touch-target) - var(--border-width) * 2)');
  });
  it('splits phone and tablet chrome at one point (no overlap at 768)', () => {
    expect(shell).not.toContain('48.0625rem');
    expect(shell).toContain('@media (width > 48rem)');
  });
});

describe('controls', () => {
  const button = read('../ui/Button.module.css');
  const control = read('../ui/control.module.css');
  it('maps the three button sizes to 32, 40 and 48 and pads the hit area on touch', () => {
    expect(button).toMatch(/\.root \{[^}]*--button-size: var\(--control-md\)/);
    expect(button).toMatch(/\.sm \{[^}]*--button-size: var\(--control-sm\)/);
    expect(button).toMatch(/\.lg \{[^}]*--button-size: var\(--control-lg\)/);
    expect(button).toMatch(/@media \(pointer: coarse\) \{\s*\.root::after/);
    expect(button).toContain('var(--touch-target)');
    expect(button).toContain('outline: var(--focus-ring-width) solid var(--color-primary)');
  });
  it('gives inputs the md height and the control radius', () => {
    expect(control).toContain('min-block-size: var(--control-md)');
    expect(control).toContain('border-radius: var(--radius-sm)');
  });
});
