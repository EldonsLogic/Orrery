'use client';

import { useTranslations } from 'next-intl';
import { Alert, Button } from '../../ui';

/** Error inside the shell: the shell stays, the content area shows this. No error detail reaches the customer. */
export default function AppError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  const t = useTranslations('shell.state.error');
  return (
    <Alert tone="danger" title={t('title')}>
      <p>{t('body')}</p>
      <Button onClick={reset}>{t('retry')}</Button>
    </Alert>
  );
}
