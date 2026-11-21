import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import type { MetadataRoute } from 'next';
import { defaultLocale, directionOf, messages } from '../i18n';
import { buildManifest, themeColorsFromTokens } from '../pwa/manifest';

export const dynamic = 'force-static';

export default function manifest(): MetadataRoute.Manifest {
  const css = readFileSync(join(process.cwd(), 'src/styles/tokens.generated.css'), 'utf8');
  const m = messages[defaultLocale].pwa;
  return buildManifest(m, themeColorsFromTokens(css), defaultLocale, directionOf(defaultLocale)) as MetadataRoute.Manifest;
}
