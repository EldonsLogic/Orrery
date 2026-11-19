'use client';

import { useTranslations } from 'next-intl';
import { useChat } from '../../chat/useChat';
import { suggestionKeys } from '../../chat/suggestions';
import type { ChatPort } from '../../chat/types';
import { Button } from '../../ui';
import { ApprovalCard, ChatError, ClarifyPrompt, ConfirmCard } from './Cards';
import { Composer } from './Composer';
import { ActivityList, MessageList, Typing } from './Messages';
import styles from './Chat.module.css';

export type ChatScreenProps = { port: ChatPort; roles: ReadonlyArray<string> };

/** One chat for every role (ADR-0004). It shows what the server streams and decides nothing itself. */
export function ChatScreen({ port, roles }: ChatScreenProps) {
  const t = useTranslations('chat');
  const { state, send, cancel, respond, setMode } = useChat(port);
  const running = state.run !== 'idle';
  const keys = suggestionKeys(roles);
  return (
    <section aria-labelledby="chat-title" className={styles.page}>
      <h1 id="chat-title" className={styles.title}>{t('title')}</h1>
      {state.messages.length === 0 && !running ? (
        <div className={styles.empty}>
          <p>{t('empty.intro')}</p>
          <ul className={styles.chips} aria-label={t('empty.suggestions')}>
            {keys.map((k) => (
              <li key={k}>
                <Button variant="secondary" size="sm" onClick={() => send(t(`suggestions.${k}`))}>
                  {t(`suggestions.${k}`)}
                </Button>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <MessageList messages={state.messages} />
      )}
      {running ? <Typing label={state.run === 'cancelling' ? t('stream.cancelling') : t('stream.working')} /> : null}
      <ActivityList steps={state.activity} />
      {state.clarifyKey ? <ClarifyPrompt clarifyKey={state.clarifyKey} /> : null}
      {state.confirm ? <ConfirmCard confirm={state.confirm} onAnswer={(ok) => respond((state.confirm as { confirmId: string }).confirmId, ok)} /> : null}
      {state.approvals.map((a) => (
        <ApprovalCard key={a.approvalId} approval={a} />
      ))}
      {state.errorCode ? <ChatError code={state.errorCode} /> : null}
      <Composer mode={state.mode} running={running} onMode={setMode} onSend={send} onCancel={cancel} />
    </section>
  );
}
