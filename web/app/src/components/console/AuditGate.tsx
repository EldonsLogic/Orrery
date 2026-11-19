'use client';

import { useTranslations } from 'next-intl';
import { Alert } from '../../ui';
import type { ViewAuditState } from './useViewAudit';

/** What a screen shows instead of data until its view audit has resolved. */
export function AuditGate({ state }: { state: Exclude<ViewAuditState, 'ok'> }) {
  const t = useTranslations('console.viewAudit');
  return state === 'failed' ? (
    <Alert tone="danger" title={t('failedTitle')}>
      {t('failedBody')}
    </Alert>
  ) : (
    <p role="status">{t('pending')}</p>
  );
}
