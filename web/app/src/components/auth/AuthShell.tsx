'use client';

import type { ReactNode } from 'react';
import { useLocale } from 'next-intl';
import { Card, Stack } from '../../ui';
import { directionOf, isLocale, defaultLocale } from '../../i18n';
import styles from './Auth.module.css';

/** Centred card on the page background. Sets lang and dir on its own root so it stands alone. */
export function AuthShell({ title, children }: { title: string; children: ReactNode }) {
  const raw = useLocale();
  const locale = isLocale(raw) ? raw : defaultLocale;
  return (
    <main className={styles.page} lang={locale} dir={directionOf(locale)}>
      <Card as="section" className={styles.panel} aria-labelledby="auth-title">
        <Stack gap={2}>
          <h1 id="auth-title" className={styles.title}>
            {title}
          </h1>
          {children}
        </Stack>
      </Card>
    </main>
  );
}
