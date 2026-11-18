'use client';

import { useTranslations } from 'next-intl';
import { Button, Stack } from '../../ui';
import { AuthShell } from './AuthShell';
import styles from './Auth.module.css';

/** Shared body of the not-found, error and global-error pages. Shows no error detail to the customer. */
export function ErrorView({ kind, onRetry }: { kind: 'notFound' | 'generic' | 'global'; onRetry?: () => void }) {
  const t = useTranslations('errors');
  return (
    <AuthShell title={t(`${kind}.title`)}>
      <p className={styles.intro}>{t(`${kind}.body`)}</p>
      <Stack gap={1} direction="row" wrap>
        {onRetry ? <Button onClick={onRetry}>{t('retry')}</Button> : null}
        <a className={styles.link} href="/login/">
          {t('home')}
        </a>
      </Stack>
    </AuthShell>
  );
}
