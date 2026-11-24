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

// The brand app icon (existing asset, never redrawn) is served as the web app icon.
const icon = resolve(here, '../../docs/brand/logo/app-icon.svg');
const iconTarget = resolve(here, '../app/public/icons/app-icon.svg');
mkdirSync(dirname(iconTarget), { recursive: true });
copyFileSync(icon, iconTarget);
