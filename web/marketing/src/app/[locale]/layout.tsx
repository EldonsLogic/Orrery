import type { ReactNode } from 'react';
import { notFound } from 'next/navigation';
import { Providers } from '../../components/Providers';
import { directionOf, isLocale, locales } from '../../i18n';
import '../../styles/tokens.generated.css';
import '../../styles/tokens.proposed.generated.css';

export const dynamicParams = false;

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
