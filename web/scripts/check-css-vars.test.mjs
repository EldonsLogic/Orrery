import test from 'node:test';
import assert from 'node:assert/strict';
import { copyFileSync, mkdirSync, mkdtempSync, realpathSync, rmSync, writeFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
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

// CLI on a clean tree: no generated CSS exists, so every variable must come from the committed token files.
// The temp tree mirrors the repo layout (web/scripts and docs/brand/tokens) because the script resolves tokens relative to itself.
const here = dirname(fileURLToPath(import.meta.url));
const repoTokens = resolve(here, '..', '..', 'docs', 'brand', 'tokens');
function cleanTree(extraCss) {
  // realpath: on macOS tmpdir() sits under a symlink, and the script's CLI guard compares real paths.
  const root = realpathSync(mkdtempSync(join(tmpdir(), 'cssvars-cli-')));
  mkdirSync(join(root, 'docs', 'brand', 'tokens'), { recursive: true });
  for (const f of ['tokens.css', 'tokens.proposed.css']) copyFileSync(join(repoTokens, f), join(root, 'docs', 'brand', 'tokens', f));
  mkdirSync(join(root, 'web', 'scripts'), { recursive: true });
  copyFileSync(join(here, 'check-css-vars.mjs'), join(root, 'web', 'scripts', 'check-css-vars.mjs'));
  for (const app of ['app', 'marketing']) mkdirSync(join(root, 'web', app, 'src'), { recursive: true });
  writeFileSync(join(root, 'web', 'app', 'src', 'Btn.module.css'),
    '.btn { color: var(--color-primary-label); background: var(--color-primary-hover); }\n' +
    '.btn:active { background: var(--color-primary-pressed); }\n.muted { color: var(--color-text-muted); }\n' + extraCss);
  return root;
}
const runCli = (root) => spawnSync(process.execPath, [join(root, 'web', 'scripts', 'check-css-vars.mjs')], { encoding: 'utf8' });

test('CLI passes on a clean tree with no generated CSS, using only the committed token files', () => {
  const root = cleanTree('');
  try {
    const r = runCli(root);
    assert.equal(r.status, 0, r.stderr);
    assert.match(r.stdout, /check-css-vars: ok/);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});
test('CLI still fails on a truly undefined variable on a clean tree', () => {
  const root = cleanTree('.x { color: var(--color-definitely-not-defined); }\n');
  try {
    const r = runCli(root);
    assert.equal(r.status, 1);
    assert.match(r.stderr, /undefined CSS variable --color-definitely-not-defined/);
    assert.doesNotMatch(r.stderr, /--color-primary-hover|--color-text-muted|--color-primary-label|--color-primary-pressed/);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});
