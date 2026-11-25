'use client';

import { useTranslations } from 'next-intl';
import { Badge } from '../../ui';
import { LoadingMark } from '../marks/LoadingMark';
import { textLang } from '../../chat/text';
import type { ActivityStep, ChatMessage, ToolOutcome } from '../../chat/types';
import styles from './Chat.module.css';

/**
 * Message text is rendered as a React text child only (never HTML), inside an isolated bubble with
 * dir="auto" so Arabic and English mix without reordering the neighbours. Links are plain text.
 */
export function MessageList({ messages }: { messages: ReadonlyArray<ChatMessage> }) {
  const t = useTranslations('chat.roles');
  return (
    <ol className={styles.log} aria-label={t('log')} aria-live="polite" aria-relevant="additions text" aria-busy={messages.some((m) => m.streaming) || undefined}>
      {messages.map((m) => (
        <li key={m.id} className={`${styles.row} ${m.role === 'user' ? styles.rowUser : ''}`} data-role={m.role}>
          <div className={`${styles.bubble} ${styles[m.role]}`} dir="auto">
            <span className={styles.meta}>{t(m.role)}</span>
            <bdi lang={textLang(m.text)}>{m.text}</bdi>
            {m.streaming ? <span className={styles.cursor} aria-hidden="true"> ▍</span> : null}
          </div>
        </li>
      ))}
    </ol>
  );
}

const TONE: Record<ToolOutcome | 'running', 'success' | 'warning' | 'danger' | 'neutral'> = {
  running: 'neutral',
  ok: 'success',
  pending_approval: 'warning',
  denied: 'danger',
  error: 'danger',
};

/** Tool name, risk class and outcome only. Arguments and results never reach this list. */
export function ActivityList({ steps }: { steps: ReadonlyArray<ActivityStep> }) {
  const t = useTranslations('chat.activity');
  if (!steps.length) return null;
  return (
    <section aria-label={t('title')}>
      <h2 className={styles.cardTitle}>{t('title')}</h2>
      <ul className={styles.steps}>
        {steps.map((s) => (
          <li key={s.callId} className={styles.step}>
            <bdi className={styles.tool} lang="en">{s.tool}</bdi>
            <Badge tone="neutral" aria-label={t('risk', { risk: s.risk })}>{s.risk}</Badge>
            <Badge tone={TONE[s.outcome]}>{t(`outcome.${s.outcome}`)}</Badge>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Seshna is working on a reply: the brand loading mark with its visible label. */
export function Typing({ label }: { label: string }) {
  return <LoadingMark label={label} className={styles.typing} />;
}
