import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { definedIn, scanApp, scanCss } from './check-css-vars.mjs';

const tokens = definedIn(':root{--color-text:#000;--space-2:8px}');
const names = (css) => scanCss(css, tokens).map((x) => x.name);

test('reads definitions from token CSS', () => {
  assert.deepEqual([...tokens].sort(), ['--color-text', '--space-2']);
});
test('defined token variables pass', () => {
  assert.deepEqual(names('.a { color: var(--color-text); gap: var( --space-2 ); }'), []);
});
test('undefined variables are reported with line number', () => {
  assert.deepEqual(scanCss('.a {\n color: var(--color-text-muted);\n}', tokens).map((x) => [x.name, x.line]), [['--color-text-muted', 2]]);
});
test('variables defined locally in the same file pass', () => {
  assert.deepEqual(names('.a { --gap: 4px; margin: var(--gap); }'), []);
});
test('an explicit fallback is allowed', () => {
  assert.deepEqual(names('.a { font-family: var(--font-mono, var(--color-text)); }'), []);
  assert.deepEqual(names('.a { color: var(--nope); }'), ['--nope']);
});
test('commented-out usage is ignored', () => {
  assert.deepEqual(names('/* var(--nope) */ .a { color: var(--color-text); }'), []);
});
test('a var() split over several lines is checked, with the line of its start', () => {
  assert.deepEqual(scanCss('.a {\n  color: var(\n    --nope\n  );\n}', tokens).map((x) => [x.name, x.line]), [['--nope', 2]]);
  assert.deepEqual(names('.a { color: var(\n --color-text\n ); }'), []);
});
test('an empty fallback does not count as a fallback', () => {
  assert.deepEqual(names('.a { color: var(--nope,); }'), ['--nope']);
  assert.deepEqual(names('.a { color: var(--nope, ); }'), ['--nope']);
  assert.deepEqual(names('.a { color: var(--nope, red); }'), []);
});
test('var() inside TSX, global CSS, and with test fixtures not whitelisting is covered by scanApp', () => {
  const dir = mkdtempSync(join(tmpdir(), 'cssvars-'));
  try {
    mkdirSync(join(dir, 'src', 'x'), { recursive: true });
    writeFileSync(join(dir, 'src', 'g.css'), '.g { color: var(--g-missing); }\n');
    writeFileSync(join(dir, 'src', 'x', 'C.tsx'), "export const C = () => <i style={{ color: 'var(--tsx-missing)' }} />;\n");
    writeFileSync(join(dir, 'src', 'x', 'C.test.tsx'), "const s = { '--fixture-only': 1 };\n");
    writeFileSync(join(dir, 'src', 'x', 'C.module.css'), '.m { color: var(--fixture-only); }\n');
    const found = scanApp(dir, ':root{--color-text:#000}').map((f) => f.name).sort();
    assert.deepEqual(found, ['--fixture-only', '--g-missing', '--tsx-missing']);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});
