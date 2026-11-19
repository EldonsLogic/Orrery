// RTL layout check (QA-008). Fails on physical-direction CSS that breaks in dir="rtl".
// Deterministic and baseline-free: no screenshots. Escape hatch: a `/* rtl-ok: reason */`
// comment on the same line or the line above. Scans every *.css under app/src and marketing/src.
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const SKIP_DIRS = new Set(['node_modules', '.next', 'out']);
const START = String.raw`(?:^|[\s;{])`;

const RULES = [
  { id: 'physical-box', re: new RegExp(`${START}(?:margin|padding|border|scroll-margin|scroll-padding)-(?:left|right)(?:-[a-z]+)*\\s*:`, 'i'), msg: 'use margin/padding/border-inline-start|end' },
  { id: 'physical-radius', re: /border-(?:top|bottom)-(?:left|right)-radius\s*:/i, msg: 'use border-start-start-radius etc.' },
  { id: 'physical-offset', re: new RegExp(`${START}(?:left|right)\\s*:`, 'i'), msg: 'use inset-inline-start|end' },
  { id: 'physical-align', re: /(?:text-align|text-align-last|float|clear|caption-side)\s*:\s*(?:left|right)\b/i, msg: 'use start/end or inline-start/inline-end' },
  { id: 'physical-resize', re: /\bresize\s*:\s*(?:horizontal)\b/i, msg: 'horizontal resize is physical; use inline' },
  { id: 'physical-origin', re: /(?:transform-origin|background-position|object-position)\s*:[^;]*\b(?:left|right)\b/i, msg: 'physical keyword; use logical or flip per direction' },
  { id: 'translate-x', re: /\b(?:translateX|translate3d|translate)\(\s*[^)]*\)/i, msg: 'translate does not mirror; use inset-inline or a [dir=rtl] counterpart' },
  { id: 'rotate-scale-x', re: /\b(?:scaleX|rotateY)\(/i, msg: 'directional flip must have a [dir=rtl] counterpart' },
];

const OK = /\/\*\s*rtl-ok:\s*\S[^*]*\*\//;

export function scanText(text, file = '<memory>') {
  const out = [];
  const lines = text.split('\n');
  lines.forEach((line, i) => {
    if (OK.test(line) || (i > 0 && OK.test(lines[i - 1]) && lines[i - 1].trim().startsWith('/*'))) return;
    // A rule that already lists a [dir=rtl] selector on the line is treated as the counterpart.
    if (/\[dir=["']?rtl["']?\]|:dir\(rtl\)/.test(line)) return;
    for (const r of RULES) if (r.re.test(line)) out.push({ file, line: i + 1, rule: r.id, msg: r.msg });
  });
  return out;
}

function* walk(dir) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) {
      if (!SKIP_DIRS.has(name)) yield* walk(p);
    } else if (name.endsWith('.css')) yield p;
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
  console.log('check-rtl-css: ok');
}
