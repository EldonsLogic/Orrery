// Copies the generated brand tokens into each app at build time. Never hand-edit the copies.
import { copyFileSync, mkdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const source = resolve(here, '../../docs/brand/tokens/tokens.css');

for (const app of ['app', 'marketing']) {
  const target = resolve(here, '..', app, 'src/styles/tokens.generated.css');
  mkdirSync(dirname(target), { recursive: true });
  copyFileSync(source, target);
}

// The brand app icon (existing asset, never redrawn) is served as the web app icon.
const icon = resolve(here, '../../docs/brand/logo/app-icon.svg');
const iconTarget = resolve(here, '../app/public/icons/app-icon.svg');
mkdirSync(dirname(iconTarget), { recursive: true });
copyFileSync(icon, iconTarget);
