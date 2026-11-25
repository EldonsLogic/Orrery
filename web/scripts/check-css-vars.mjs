// Rejects var(--x) in web CSS and TSX when --x is neither defined in the brand tokens CSS nor in the same file.
// An undefined variable silently falls back to the initial value (QA-014 A-01: unreadable bubbles). Token files are only read.
// Defined means: in docs/brand/tokens/tokens.css, in any global (non-module) stylesheet, as an inline style key in non-test TSX, or
// locally in the file. A var() with a non-empty fallback is allowed: the author chose it. `var(--x,)` (empty fallback) is not.
// Scans CSS modules, global stylesheets and var() inside TSX; multi-line var() is handled.
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const SKIP_DIRS = new Set(['node_modules', '.next', 'out']);
const TOKENS = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', 'docs', 'brand', 'tokens', 'tokens.css');
const isTest = (f) => /\.(test|spec)\.[cm]?[jt]sx?$/.test(f) || f.split(/[\\/]/).includes('__tests__');

const strip = (css) => css.replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, ' '));
export const definedIn = (css) => new Set([...strip(css).matchAll(/(--[\w-]+)\s*:/g)].map((m) => m[1]));

export function scanCss(css, tokens, file = '<memory>') {
  const local = definedIn(css);
  const text = strip(css);
  const out = [];
  // Whole-text scan so a var( split over lines is still seen; an empty fallback (var(--x,)) counts as no fallback.
  for (const m of text.matchAll(/var\(\s*(--[\w-]+)\s*(?:(,)\s*([^\s)]?))?/g)) {
    if (m[2] === ',' && m[3] !== '' && m[3] !== undefined) continue;
    if (tokens.has(m[1]) || local.has(m[1])) continue;
    out.push({ file, line: text.slice(0, m.index).split('\n').length, name: m[1] });
  }
  return out;
}

function* walk(dir, ext) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) {
      if (!SKIP_DIRS.has(name)) yield* walk(p, ext);
    } else if (ext.test(name)) yield p;
  }
}

export function scanApp(appDir, tokensCss = readFileSync(TOKENS, 'utf8')) {
  const src = join(appDir, 'src');
  const read = (f) => readFileSync(f, 'utf8');
  const global = new Set(definedIn(tokensCss));
  for (const f of walk(src, /\.css$/)) if (!f.endsWith('.module.css')) definedIn(read(f)).forEach((n) => global.add(n));
  // Inline style keys count as definitions only in app code; a test fixture must not whitelist a name for the whole app.
  for (const f of walk(src, /\.tsx?$/)) if (!isTest(f)) for (const m of read(f).matchAll(/['"](--[\w-]+)['"]\s*:/g)) global.add(m[1]);
  const files = [...walk(src, /\.css$/), ...[...walk(src, /\.tsx$/)].filter((f) => !isTest(f))];
  return files.flatMap((f) => scanCss(read(f), global, f));
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
  const found = ['app', 'marketing'].flatMap((a) => scanApp(join(root, a)));
  for (const f of found) console.error(`${relative(root, f.file)}:${f.line} undefined CSS variable ${f.name}`);
  if (found.length) process.exit(1);
  console.log('check-css-vars: ok');
}
