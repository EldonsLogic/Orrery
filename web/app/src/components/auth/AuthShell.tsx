'use client';

import type { ReactNode } from 'react';
import { useLocale } from 'next-intl';
import { Card, Stack } from '../../ui';
import { directionOf, isLocale, defaultLocale } from '../../i18n';
import styles from './Auth.module.css';

/** Centred card on the page background. `brand` and `tenant` are the WEB-008 tenant look (login only). Sets lang and dir on its own root so it stands alone. */
export function AuthShell({ title, children, brand, tenant }: { title: string; children: ReactNode; brand?: ReactNode; tenant?: string }) {
  const raw = useLocale();
  const locale = isLocale(raw) ? raw : defaultLocale;
  return (
    <main className={styles.page} lang={locale} dir={directionOf(locale)} data-tenant={tenant}>
      <Card as="section" className={styles.panel} aria-labelledby="auth-title">
        <Stack gap={2}>
          {brand}
          <h1 id="auth-title" className={styles.title}>
            {title}
          </h1>
          {children}
        </Stack>
      </Card>
    </main>
  );
}
