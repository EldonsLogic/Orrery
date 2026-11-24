import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import type { Metadata, Viewport } from 'next';
import type { ReactNode } from 'react';
import { Providers } from '../components/Providers';
import { defaultLocale, directionOf, messages } from '../i18n';
import { themeColorsFromTokens } from '../pwa/manifest';
import '../styles/tokens.generated.css';
import '../styles/tokens.proposed.generated.css';
import '../styles/mobile.css';

export const metadata: Metadata = {
  title: messages[defaultLocale].pwa.name,
  description: messages[defaultLocale].pwa.description,
  icons: { icon: '/icons/app-icon.svg', apple: '/icons/app-icon.svg' },
  appleWebApp: { capable: true, title: messages[defaultLocale].pwa.shortName, statusBarStyle: 'default' },
};

// theme-color per scheme comes from the generated tokens (see pwa/manifest.ts); the manifest carries the light one.
export function generateViewport(): Viewport {
  const css = readFileSync(join(process.cwd(), 'src/styles/tokens.generated.css'), 'utf8');
  const c = themeColorsFromTokens(css);
  return {
    width: 'device-width',
    initialScale: 1,
    viewportFit: 'cover',
    themeColor: [
      { media: '(prefers-color-scheme: light)', color: c.light },
      { media: '(prefers-color-scheme: dark)', color: c.dark },
    ],
  };
}

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang={defaultLocale} dir={directionOf(defaultLocale)} suppressHydrationWarning>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
