'use client';

import Link from 'next/link';
import { useLocale, useTranslations } from 'next-intl';
import type { ReactNode } from 'react';
import { Badge, Icon, Mark, VisuallyHidden } from '../../ui';
import { LoadingMark } from '../marks/LoadingMark';
import { textLang } from '../../chat/text';
import { sourceHref } from '../../chat/events';
import { toolPhrase } from '../../chat/labels';
import { fixtureData } from '../../records/fixture/rows';
import { pick } from '../../records/labels';
import type { ActivityStep, ChatMessage, SourceRef, ToolOutcome } from '../../chat/types';
import styles from './Chat.module.css';

/** An action in words ("Update sales order SO-00006"), never the tool id. */
export function ActionLabel({ tool, record }: { tool: string; record?: SourceRef }) {
  const t = useTranslations('chat.tools');
  const locale = useLocale();
  const p = toolPhrase(fixtureData, tool, locale);
  return (
    <>
      {t(p.key, { entity: p.entity })}
      {record ? (
        <>
          {' '}
          <bdi dir="ltr" className={styles.recordId}>
            {record.id}
          </bdi>
        </>
      ) : null}
    </>
  );
}

/** A Seshna turn: the mark at the start, the name, then the content at full column width (no bubble). */
export function SeshnaTurn({ children, role, busy }: { children: ReactNode; role?: 'note'; busy?: boolean }) {
  const t = useTranslations('chat.roles');
  return (
    <div className={styles.seshna} role={role} aria-busy={busy || undefined}>
      <span className={styles.avatar}>
        <Mark upper="solid" lower="solid" size={20} />
      </span>
      <div className={styles.turnBody}>
        <span className={styles.name}>
          <bdi>{t('assistant')}</bdi>
        </span>
        {children}
      </div>
    </div>
  );
}

/**
 * Message text is rendered as a React text child only (never HTML), isolated with dir="auto" so Arabic and English mix
 * without reordering the neighbours. Links in text stay plain text; only validated source records become links.
 */
export function MessageList({ messages }: { messages: ReadonlyArray<ChatMessage> }) {
  const t = useTranslations('chat.roles');
  return (
    <ol className={styles.log} aria-label={t('log')} aria-live="polite" aria-relevant="additions text" aria-busy={messages.some((m) => m.streaming) || undefined}>
      {messages.map((m) => (
        <li key={m.id} className={styles.row} data-role={m.role}>
          {m.role === 'assistant' ? (
            <SeshnaTurn>
              <p className={styles.text} dir="auto">
                <bdi lang={textLang(m.text)}>{m.text}</bdi>
                {m.streaming ? <span className={styles.caret} aria-hidden="true" /> : null}
              </p>
              {m.sources?.length && !m.streaming ? <Sources sources={m.sources} /> : null}
            </SeshnaTurn>
          ) : m.role === 'user' ? (
            <div className={styles.userPill} dir="auto">
              <VisuallyHidden>{t('user')}: </VisuallyHidden>
              <bdi lang={textLang(m.text)} className={styles.text}>
                {m.text}
              </bdi>
            </div>
          ) : (
            <p className={styles.system} dir="auto">
              <VisuallyHidden>{t('system')}: </VisuallyHidden>
              <bdi lang={textLang(m.text)}>{m.text}</bdi>
            </p>
          )}
        </li>
      ))}
    </ol>
  );
}

/** The records an answer came from, as chips that open each record. The record screen checks access again. */
function Sources({ sources }: { sources: ReadonlyArray<SourceRef> }) {
  const t = useTranslations('chat.sources');
  const locale = useLocale();
  return (
    <div className={styles.sources}>
      <span className={styles.sourcesLabel}>{t('label')}</span>
      <ul className={styles.sourceList}>
        {sources.map((s) => {
          const entity = fixtureData.entities.find((e) => e.id === s.entity);
          return (
            <li key={`${s.entity}/${s.id}`}>
              <Link href={sourceHref(s)} className={styles.sourceChip} aria-label={t('open', { record: s.id })}>
                <Icon name="file" />
                {entity ? <span className={styles.sourceKind}>{pick(entity.labels, locale, entity.id)}</span> : null}
                <bdi dir="ltr" className={styles.sourceId}>
                  {s.id}
                </bdi>
              </Link>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

const TONE: Record<ToolOutcome | 'running', 'success' | 'warning' | 'danger' | 'neutral'> = {
  running: 'neutral',
  ok: 'success',
  pending_approval: 'warning',
  denied: 'danger',
  error: 'danger',
};

/** The action in words and its outcome only; the tool id and risk class stay in data attributes. Arguments and results never reach this list. */
export function ActivityList({ steps, open = false }: { steps: ReadonlyArray<ActivityStep>; open?: boolean }) {
  const t = useTranslations('chat.activity');
  if (!steps.length) return null;
  return (
    <details className={styles.activity} open={open || undefined} aria-label={t('title')}>
      <summary className={styles.activitySummary}>
        <Icon name="chevronDown" className={styles.activityChevron} />
        <span>{t('title')}</span>
        <span className={styles.activityCount}>{t('summary', { count: steps.length })}</span>
      </summary>
      <ul className={styles.steps}>
        {steps.map((s) => (
          <li key={s.callId} className={styles.step} data-tool={s.tool} data-risk={s.risk}>
            <span>
              <ActionLabel tool={s.tool} />
            </span>
            <Badge tone={TONE[s.outcome]}>{t(`outcome.${s.outcome}`)}</Badge>
          </li>
        ))}
      </ul>
    </details>
  );
}

/** Seshna is working on a reply: a Seshna turn holding the brand loading mark with its visible label (static under reduced motion). */
export function Thinking({ label }: { label: string }) {
  // The loading mark takes the avatar's place, so the turn shows one mark, not two.
  return (
    <div className={styles.thinkingRow}>
      <LoadingMark label={label} className={styles.thinking} />
    </div>
  );
}

/** Kept for callers of the WEB-004 name. */
export const Typing = Thinking;
