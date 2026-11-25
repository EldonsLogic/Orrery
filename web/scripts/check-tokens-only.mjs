// Rejects colour literals, font-family literals and physical-direction CSS in web sources
// (ADR-0022, AGENTS.md "tokens only"). Token files are exempt.
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const EXEMPT = /(^|\/)tokens(\.proposed)?(\.generated)?\.css$/;
// The @font-face file names the families once; every other font-family stays token-only.
const FACE_FILE = /(^|\/)styles\/fonts\.css$/;
const EXT = /\.(css|ts|tsx)$/;
const SKIP_DIRS = new Set(['node_modules', '.next', 'out', 'theme']);

const RULES = [
  { id: 'colour-hex', re: /#[0-9a-fA-F]{3,8}\b/, msg: 'hex colour literal; use a var(--color-*) token' },
  { id: 'colour-fn', re: /\b(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch|color)\(/i, msg: 'colour function literal; use a var(--color-*) token' },
  { id: 'font-family', re: /font-family\s*:(?!\s*var\()/i, msg: 'font-family literal; use var(--font-*)' },
  { id: 'font-family-js', re: /\bfontFamily\s*:(?!\s*['"`]?var\()/, msg: 'fontFamily literal; use var(--font-*)' },
  { id: 'physical-prop', re: /(?:^|[\s;{"'`])(?:margin|padding|border)-(?:left|right)(?:-[a-z]+)?\s*:/i, msg: 'physical property; use logical (inline-start/end)' },
  { id: 'physical-radius', re: /border-(?:top|bottom)-(?:left|right)-radius\s*:/i, msg: 'physical radius; use start-start/end-end etc.' },
  { id: 'physical-offset', re: /(?:^|[\s;{"'`])(?:left|right)\s*:/i, msg: 'physical offset; use inset-inline-start/end' },
  { id: 'physical-align', re: /(?:text-align|float|clear)\s*:\s*(?:left|right)\b/i, msg: 'physical alignment; use start/end' },
  { id: 'physical-js', re: /\b(?:margin|padding|border)(?:Left|Right)\b|\btextAlign\s*:\s*['"](?:left|right)['"]/, msg: 'physical style key; use logical properties' },
];

export function scanText(text, file = '<memory>') {
  const out = [];
  if (EXEMPT.test(file.replaceAll('\\', '/'))) return out;
  text.split('\n').forEach((line, i) => {
    for (const r of RULES) if (!(r.id === 'font-family' && FACE_FILE.test(file.replaceAll('\\', '/'))) && r.re.test(line)) out.push({ file, line: i + 1, rule: r.id, msg: r.msg });
  });
  return out;
}

function* walk(dir) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) {
      if (!SKIP_DIRS.has(name)) yield* walk(p);
    } else if (EXT.test(name)) yield p;
  }
}

export function scanDirs(dirs) {
  return dirs.flatMap((d) => [...walk(d)].flatMap((f) => scanText(readFileSync(f, 'utf8'), f)));
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
  const found = scanDirs(['app/src', 'marketing/src'].map((d) => join(root, d)));
  for (const f of found) console.error(`${relative(root, f.file)}:${f.line} [${f.rule}] ${f.msg}`);
  if (found.length) process.exit(1);
  console.log('check-tokens-only: ok');
}
