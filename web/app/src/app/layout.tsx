import type { ReactNode } from 'react';
import { Providers } from '../components/Providers';
import { defaultLocale, directionOf } from '../i18n';
import '../styles/tokens.generated.css';

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang={defaultLocale} dir={directionOf(defaultLocale)} suppressHydrationWarning>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
