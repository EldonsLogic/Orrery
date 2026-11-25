// Copies the generated brand tokens into each app at build time. Never hand-edit the copies.
import { copyFileSync, mkdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const tokens = resolve(here, '../../docs/brand/tokens');
// tokens.css first, then the accepted v1.1 layer (Q-70), which the apps load after it.
const sources = [
  ['tokens.css', 'tokens.generated.css'],
  ['tokens.proposed.css', 'tokens.proposed.generated.css'],
];

for (const app of ['app', 'marketing']) {
  for (const [from, to] of sources) {
    const target = resolve(here, '..', app, 'src/styles', to);
    mkdirSync(dirname(target), { recursive: true });
    copyFileSync(resolve(tokens, from), target);
  }
}

// Brand icons (generated in docs/brand/logo by docs/brand/tools, never redrawn here) are served from /icons/ in each app.
const logo = resolve(here, '../../docs/brand/logo');
const ICONS = {
  'app-icon.svg': 'app-icon.svg',
  'favicon.svg': 'mark-small.svg',
  'favicon.ico': 'png/favicon.ico',
  'apple-touch-icon.png': 'png/apple-touch-icon.png',
  'icon-192.png': 'png/app-icon-192.png',
  'icon-512.png': 'png/app-icon-512.png',
  'maskable-512.png': 'png/maskable-512.png',
};
for (const app of ['app', 'marketing']) {
  const dir = resolve(here, '..', app, 'public/icons');
  mkdirSync(dir, { recursive: true });
  for (const [target, src] of Object.entries(ICONS)) copyFileSync(resolve(logo, src), resolve(dir, target));
}
