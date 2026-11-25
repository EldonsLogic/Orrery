'use client';

import Link from 'next/link';
import { useTranslations } from 'next-intl';
import { Alert, Button, Card, Stack } from '../../ui';
import type { PendingApproval, PendingConfirm } from '../../chat/types';
import { StatusMark } from '../marks/StatusMark';
import styles from './Chat.module.css';

/** Confirm-before-write in the ConfirmWrite style. It only asks; it never confirms by itself. */
export function ConfirmCard({ confirm, onAnswer }: { confirm: PendingConfirm; onAnswer: (accepted: boolean) => void }) {
  const t = useTranslations('chat.confirm');
  return (
    <Card as="section" aria-labelledby="chat-confirm-title">
      <Stack gap={2}>
        <h2 id="chat-confirm-title" className={styles.cardTitle}>{t('title')}</h2>
        <p>{t('intro', { tool: confirm.tool, risk: confirm.risk })}</p>
        {confirm.changes.length ? (
          <ul className={styles.changes} aria-label={t('changes')}>
            {confirm.changes.map((c, i) => (
              <li key={i} dir="auto">
                {t('change', { field: c.label, before: c.before || t('empty'), after: c.after || t('empty') })}
              </li>
            ))}
          </ul>
        ) : (
          <p>{t('noChanges')}</p>
        )}
        <Stack direction="row" gap={1} wrap>
          <Button onClick={() => onAnswer(true)}>{t('confirm')}</Button>
          <Button variant="secondary" onClick={() => onAnswer(false)}>{t('cancel')}</Button>
        </Stack>
      </Stack>
    </Card>
  );
}

/** A pending approval. Chat has no approve action (ADR-0044): it links to the approval inbox. */
export function ApprovalCard({ approval }: { approval: PendingApproval }) {
  const t = useTranslations('chat.approval');
  return (
    <Alert tone="warning" title={t('title')}>
      <p>
        <StatusMark status="drafted" />
      </p>
      <p>{t('body', { tool: approval.tool, risk: approval.risk })}</p>
      <Link href="/approvals/">{t('open')}</Link>
    </Alert>
  );
}

export function ClarifyPrompt({ clarifyKey }: { clarifyKey: string }) {
  const t = useTranslations('chat.clarify');
  const known = ['whichRecord', 'whichPeriod', 'whichAction', 'generic'];
  return (
    <Alert tone="info" role="note" title={t('title')}>
      {t(known.includes(clarifyKey) ? clarifyKey : 'generic')}
    </Alert>
  );
}

export function ChatError({ code }: { code: string }) {
  const t = useTranslations('chat.errors');
  const known = ['forbidden', 'rate_limited', 'unavailable', 'invalid_request', 'cancelled', 'timeout'];
  return (
    <Alert tone="danger" title={t('title')}>
      {t(known.includes(code) ? code : 'unknown')}
    </Alert>
  );
}
