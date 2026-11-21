// Rejects var(--x) in web CSS modules when --x is neither defined in the generated tokens CSS nor in the same file.
// An undefined variable silently falls back to the initial value (QA-014 A-01: unreadable bubbles). Token files are only read.
// Defined means: in the generated tokens, in any global (non-module) stylesheet, as an inline style key in TSX, or locally in the file.
// A var() with an explicit fallback is allowed: the author chose it.
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const SKIP_DIRS = new Set(['node_modules', '.next', 'out']);

const strip = (css) => css.replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, ' '));
export const definedIn = (css) => new Set([...strip(css).matchAll(/(--[\w-]+)\s*:/g)].map((m) => m[1]));

export function scanCss(css, tokens, file = '<memory>') {
  const local = definedIn(css);
  const out = [];
  strip(css).split('\n').forEach((line, i) => {
    for (const m of line.matchAll(/var\(\s*(--[\w-]+)\s*([,)])/g)) {
      if (m[2] === ',') continue;
      if (!tokens.has(m[1]) && !local.has(m[1])) out.push({ file, line: i + 1, name: m[1] });
    }
  });
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

export function scanApp(appDir) {
  const src = join(appDir, 'src');
  const read = (f) => readFileSync(f, 'utf8');
  const global = new Set(definedIn(read(join(src, 'styles/tokens.generated.css'))));
  for (const f of walk(src, /\.css$/)) if (!f.endsWith('.module.css')) definedIn(read(f)).forEach((n) => global.add(n));
  for (const f of walk(src, /\.tsx?$/)) for (const m of read(f).matchAll(/['"](--[\w-]+)['"]\s*:/g)) global.add(m[1]);
  return [...walk(src, /\.module\.css$/)].flatMap((f) => scanCss(read(f), global, f));
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
  const found = ['app', 'marketing'].flatMap((a) => scanApp(join(root, a)));
  for (const f of found) console.error(`${relative(root, f.file)}:${f.line} undefined CSS variable ${f.name}`);
  if (found.length) process.exit(1);
  console.log('check-css-vars: ok');
}
