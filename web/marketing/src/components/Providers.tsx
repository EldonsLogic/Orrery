'use client';

import type { ReactNode } from 'react';
import { NextIntlClientProvider } from 'next-intl';
import { messages, type Locale } from '../i18n';

// A client boundary keeps next-intl's server-side config lookup out of the static export.
export function Providers({ locale, children }: { locale: Locale; children: ReactNode }) {
  return (
    <NextIntlClientProvider locale={locale} messages={messages[locale]} timeZone="UTC">
      {children}
    </NextIntlClientProvider>
  );
}
