import test from 'node:test';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';
import { PAIRS_ALL, evaluate, mix, ratio, readSource, readThemes, tokenCss } from './check-contrast.mjs';

// Pairs that fail AA and are tracked in docs/specs/qa-014-accessibility-audit.md (A-12). Token values are generated and not
// edited here; a listed pair runs as a known failure (node:test todo) so CI stays green. Format: 'mode id' -> reason.
const KNOWN = {};

const themes = readThemes(tokenCss());

test('ratio matches published WCAG values', () => {
  assert.equal(ratio('#000000', '#ffffff').toFixed(2), '21.00');
  assert.equal(ratio('#767676', '#ffffff').toFixed(2), '4.54');
  assert.equal(mix('#000000', 0.5, '#ffffff'), '#808080');
});

test('both themes are read from the brand tokens', () => {
  for (const mode of ['light', 'dark']) {
    for (const k of ['color-background', 'color-surface', 'color-text', 'color-primary', 'color-success', 'color-warning', 'color-danger']) {
      assert.match(themes[mode][k], /^#[0-9A-F]{6}$/i, `${mode} ${k}`);
    }
  }
  assert.notEqual(themes.light['color-background'], themes.dark['color-background']);
});

test('every pair is traceable to a CSS module snippet', () => {
  for (const p of PAIRS_ALL) assert.ok(readSource(p.file).includes(p.snippet), `${p.id}: "${p.snippet}" not found in ${p.file}`);
});

for (const r of evaluate(themes)) {
  const key = `${r.mode} ${r.id}`;
  const name = `${key}: ${r.label} >= ${r.min}:1`;
  const body = () => assert.ok(r.ratio >= r.min, `${key} is ${r.ratio.toFixed(2)}:1, needs ${r.min}:1`);
  if (KNOWN[key]) test(name, { todo: KNOWN[key] }, body);
  else test(name, body);
}

test('the CLI exits 0 and says ok when every pair passes', () => {
  const r = spawnSync(process.execPath, [fileURLToPath(import.meta.resolve('./check-contrast.mjs'))], { encoding: 'utf8' });
  assert.equal(r.status, 0, r.stderr);
  assert.match(r.stdout, /check-contrast: ok/);
});

test('every var(--color-*) pair in the user bubble label is on the contrast list', () => {
  assert.ok(PAIRS_ALL.some((p) => p.id === 'user-bubble-meta'));
});

test('the current nav icon and its start-edge indicator (primary on the 14% tint over glass) are on the contrast list', () => {
  for (const bn of ['white', 'black']) assert.ok(PAIRS_ALL.some((p) => p.id === `glass-current-nav-icon/${bn}` && p.min === 3), bn);
});
