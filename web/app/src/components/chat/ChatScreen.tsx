'use client';

import { useEffect, useRef } from 'react';
import { useTranslations } from 'next-intl';
import { useChat } from '../../chat/useChat';
import { suggestionKeys } from '../../chat/suggestions';
import type { ChatPort } from '../../chat/types';
import { Mark } from '../../ui';
import { ApprovalCard, ChatError, ClarifyPrompt, ConfirmCard } from './Cards';
import { Composer } from './Composer';
import { ActivityList, MessageList, Thinking } from './Messages';
import styles from './Chat.module.css';

export type ChatScreenProps = { port: ChatPort; roles: ReadonlyArray<string> };

const reducedMotion = () => typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

/**
 * One chat for every role (ADR-0004). It shows what the server streams and decides nothing itself. Layout: one calm
 * column (the chat measure), Seshna turns at full width with the mark, the person's turns as a pill at the end side, and
 * the composer docked at the bottom in glass.
 */
export function ChatScreen({ port, roles }: ChatScreenProps) {
  const t = useTranslations('chat');
  const { state, send, cancel, respond, setMode } = useChat(port);
  const running = state.run !== 'idle';
  const keys = suggestionKeys(roles);
  const input = useRef<HTMLTextAreaElement>(null);
  const streaming = state.messages.some((m) => m.streaming);
  const last = state.messages.at(-1);

  // Keep the newest turn in view as it arrives: scroll the page to its end, so the last turn sits just above the docked
  // composer (instantly when the reader prefers reduced motion).
  useEffect(() => {
    if (state.messages.length === 0) return;
    window.scrollTo?.({ top: document.documentElement.scrollHeight, behavior: reducedMotion() ? 'auto' : 'smooth' });
  }, [state.messages.length, last?.text.length, state.confirm, state.approvals.length, state.errorCode, state.clarifyKey]);

  const empty = state.messages.length === 0 && !running;
  return (
    <section aria-labelledby="chat-title" className={styles.page}>
      <h1 id="chat-title" className={styles.srOnly}>
        {t('title')}
      </h1>
      <div className={styles.column}>
        {empty ? (
          <div className={styles.empty}>
            <Mark upper="solid" lower="solid" size={32} />
            <h2 className={styles.emptyTitle}>{t('empty.title')}</h2>
            <p className={styles.emptyIntro}>{t('empty.intro')}</p>
            <ul className={styles.prompts} aria-label={t('empty.suggestions')}>
              {keys.map((k) => (
                <li key={k}>
                  <button type="button" className={styles.prompt} onClick={() => send(t(`suggestions.${k}`))}>
                    {t(`suggestions.${k}`)}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <MessageList messages={state.messages} />
        )}
        {/* Approvals stay listed from earlier turns, so they come before the live run and its confirmation. */}
        {state.approvals.map((a) => (
          <ApprovalCard key={a.approvalId} approval={a} />
        ))}
        {running && !streaming ? <Thinking label={state.run === 'cancelling' ? t('stream.cancelling') : t('stream.working')} /> : null}
        <ActivityList steps={state.activity} open={running} />
        {/* Persistent polite live region: a card that appears after the user acts elsewhere is announced. */}
        <div aria-live="polite" aria-atomic="false" className={styles.cards}>
          {state.clarifyKey ? <ClarifyPrompt clarifyKey={state.clarifyKey} /> : null}
          {state.confirm ? (
            <ConfirmCard
              confirm={state.confirm}
              onAnswer={(ok) => respond((state.confirm as { confirmId: string }).confirmId, ok)}
              onEdit={() => {
                respond((state.confirm as { confirmId: string }).confirmId, false);
                input.current?.focus();
              }}
            />
          ) : null}
        </div>
        {state.errorCode ? <ChatError code={state.errorCode} /> : null}
      </div>
      <div className={styles.dock}>
        <Composer ref={input} mode={state.mode} running={running} onMode={setMode} onSend={send} onCancel={cancel} />
      </div>
    </section>
  );
}
