import test from 'node:test';
import assert from 'node:assert/strict';
import { definedIn, scanCss } from './check-css-vars.mjs';

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
