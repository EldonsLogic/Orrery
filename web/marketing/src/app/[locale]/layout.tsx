import type { Metadata } from 'next';
import type { ReactNode } from 'react';
import { notFound } from 'next/navigation';
import { Providers } from '../../components/Providers';
import { directionOf, isLocale, locales } from '../../i18n';
import '../../styles/tokens.generated.css';

export const dynamicParams = false;

// Brand icons, copied from docs/brand/logo to /icons/ at build time by scripts/copy-tokens.mjs.
export const metadata: Metadata = {
  icons: {
    icon: [
      { url: '/icons/favicon.ico', sizes: '48x48' },
      { url: '/icons/favicon.svg', type: 'image/svg+xml' },
    ],
    apple: '/icons/apple-touch-icon.png',
  },
};

export function generateStaticParams() {
  return locales.map((locale) => ({ locale }));
}

export default async function LocaleLayout({ children, params }: { children: ReactNode; params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  if (!isLocale(locale)) notFound();
  return (
    <html lang={locale} dir={directionOf(locale)}>
      <body>
        <Providers locale={locale}>{children}</Providers>
      </body>
    </html>
  );
}
