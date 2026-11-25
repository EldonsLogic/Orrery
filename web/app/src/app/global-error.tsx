'use client';

import { NextIntlClientProvider } from 'next-intl';
import { defaultLocale, directionOf, messages } from '../i18n';
import { ErrorView } from '../components/auth/ErrorView';
import '../styles/tokens.generated.css';
import '../styles/tokens.proposed.generated.css';

/** Replaces the root layout, so it brings its own html, body and message provider. */
export default function GlobalError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <html lang={defaultLocale} dir={directionOf(defaultLocale)}>
      <body>
        <NextIntlClientProvider locale={defaultLocale} messages={messages[defaultLocale]} timeZone="UTC">
          <ErrorView kind="global" onRetry={reset} />
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
