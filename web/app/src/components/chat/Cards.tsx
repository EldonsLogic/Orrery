'use client';

import Link from 'next/link';
import { useTranslations } from 'next-intl';
import { Alert, Button, VisuallyHidden } from '../../ui';
import { cx } from '../../ui/cx';
import button from '../../ui/Button.module.css';
import type { PendingApproval, PendingConfirm } from '../../chat/types';
import { StatusMark } from '../marks/StatusMark';
import { SeshnaTurn } from './Messages';
import styles from './Chat.module.css';

/**
 * Confirm-before-write as a proposal card: drafted by the AI, the change as a before and after table, then Confirm, Edit
 * (declines the draft and returns to the composer to say what to change) or Cancel. It only asks; it never confirms by
 * itself, and it is not an approval (ADR-0044: approvals are decided in the inbox).
 */
export function ConfirmCard({ confirm, onAnswer, onEdit }: { confirm: PendingConfirm; onAnswer: (accepted: boolean) => void; onEdit?: () => void }) {
  const t = useTranslations('chat.confirm');
  return (
    <section aria-labelledby="chat-confirm-title" className={styles.proposal}>
      <header className={styles.proposalHead}>
        <StatusMark status="drafted" className={styles.proposalStatus} />
        <span className={styles.proposalRisk}>
          <bdi lang="en" className={styles.tool}>
            {confirm.tool}
          </bdi>
          <span aria-hidden="true">·</span>
          <span>{confirm.risk}</span>
        </span>
      </header>
      <h2 id="chat-confirm-title" className={styles.proposalTitle}>
        {t('title')}
      </h2>
      <p className={styles.proposalIntro}>{t('intro', { tool: confirm.tool, risk: confirm.risk })}</p>
      {confirm.changes.length ? (
        <div className={styles.diff}>
          <div className={styles.diffHead} aria-hidden="true">
            <span>{t('field')}</span>
            <span>{t('before')}</span>
            <span>{t('after')}</span>
          </div>
          <ul className={styles.diffRows} aria-label={t('changes')}>
            {confirm.changes.map((c, i) => (
              <li key={i} className={styles.diffRow}>
                <VisuallyHidden>{t('change', { field: c.label, before: c.before || t('empty'), after: c.after || t('empty') })}</VisuallyHidden>
                <span aria-hidden="true" className={styles.diffField} dir="auto">
                  {c.label}
                </span>
                <span aria-hidden="true" className={styles.diffBefore} dir="auto">
                  <bdi>{c.before || t('empty')}</bdi>
                </span>
                <span aria-hidden="true" className={styles.diffAfter} dir="auto">
                  <bdi>{c.after || t('empty')}</bdi>
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p className={styles.proposalIntro}>{t('noChanges')}</p>
      )}
      <div className={styles.proposalActions}>
        <Button onClick={() => onAnswer(true)}>{t('confirm')}</Button>
        {onEdit ? (
          <Button variant="secondary" onClick={onEdit} aria-describedby="chat-confirm-edit">
            {t('edit')}
          </Button>
        ) : null}
        <Button variant="ghost" onClick={() => onAnswer(false)}>
          {t('cancel')}
        </Button>
      </div>
      <p className={styles.proposalNote}>
        <span>{t('note')}</span>
        {onEdit ? <VisuallyHidden id="chat-confirm-edit">{t('editHint')}</VisuallyHidden> : null}
      </p>
    </section>
  );
}

/** A pending approval as a proposal card. Chat has no approve action (ADR-0044): it links to the approval inbox. */
export function ApprovalCard({ approval }: { approval: PendingApproval }) {
  const t = useTranslations('chat.approval');
  return (
    <section aria-label={t('title')} className={styles.proposal} data-kind="approval">
      <header className={styles.proposalHead}>
        <StatusMark status="drafted" className={styles.proposalStatus} />
        <span className={styles.proposalRisk}>
          <bdi lang="en" className={styles.tool}>
            {approval.tool}
          </bdi>
          <span aria-hidden="true">·</span>
          <span>{approval.risk}</span>
        </span>
      </header>
      <h2 className={styles.proposalTitle}>{t('title')}</h2>
      <p className={styles.proposalIntro}>{t('body', { tool: approval.tool, risk: approval.risk })}</p>
      <div className={styles.proposalActions}>
        <Link href="/approvals/" className={cx(button.root, button.secondary, button.md)}>
          {t('open')}
        </Link>
      </div>
    </section>
  );
}

/** Seshna asks for the missing detail in its own turn (an abstain), never as an error. */
export function ClarifyPrompt({ clarifyKey }: { clarifyKey: string }) {
  const t = useTranslations('chat.clarify');
  const known = ['whichRecord', 'whichPeriod', 'whichAction', 'generic'];
  return (
    <SeshnaTurn role="note">
      <p className={styles.text}>
        <VisuallyHidden>{t('title')}: </VisuallyHidden>
        {t(known.includes(clarifyKey) ? clarifyKey : 'generic')}
      </p>
    </SeshnaTurn>
  );
}

/** Errors and refusals in plain words. The code only picks a known message; it is never shown. */
export function ChatError({ code }: { code: string }) {
  const t = useTranslations('chat.errors');
  const known = ['forbidden', 'rate_limited', 'unavailable', 'invalid_request', 'cancelled', 'timeout'];
  return (
    <Alert tone={code === 'cancelled' ? 'info' : 'danger'} title={t('title')} className={styles.error}>
      {t(known.includes(code) ? code : 'unknown')}
    </Alert>
  );
}
