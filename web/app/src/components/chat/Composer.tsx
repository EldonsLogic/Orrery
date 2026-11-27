'use client';

import { forwardRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Button, Icon, VisuallyHidden } from '../../ui';
import { composerKeyAction } from '../../chat/text';
import { PHONE_QUERY, useMedia } from '../../lib/useMedia';
import { MAX_MESSAGE_LENGTH, MODES, type ChatMode } from '../../chat/types';
import styles from './Chat.module.css';

export type ComposerProps = {
  mode: ChatMode;
  running: boolean;
  onMode: (m: ChatMode) => void;
  onSend: (text: string) => boolean;
  onCancel: () => void;
};

/** Shows the count only near the limit, so the composer stays quiet. */
const COUNT_FROM = Math.floor(MAX_MESSAGE_LENGTH * 0.9);

/**
 * The composer, docked at the bottom of the chat in the glass material: the message box with the mode and the send (or
 * stop) button inside it, the active mode explained underneath. Enter sends, Shift+Enter is a new line, IME-safe.
 */
export const Composer = forwardRef<HTMLTextAreaElement, ComposerProps>(function Composer({ mode, running, onMode, onSend, onCancel }, ref) {
  const t = useTranslations('chat.composer');
  const tm = useTranslations('chat.mode');
  const [text, setText] = useState('');
  const phone = useMedia(PHONE_QUERY);
  const submit = () => {
    if (!running && onSend(text)) setText('');
  };
  return (
    <form
      className={styles.composer}
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <div className={styles.field}>
        <label htmlFor="chat-input" className={styles.srOnly}>
          {t('label')}
        </label>
        <textarea
          ref={ref}
          id="chat-input"
          className={styles.textarea}
          dir="auto"
          rows={1}
          value={text}
          maxLength={MAX_MESSAGE_LENGTH}
          readOnly={running}
          aria-disabled={running || undefined}
          placeholder={t(phone ? 'placeholderShort' : 'placeholder')}
          aria-describedby="chat-input-hint chat-mode-description"
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (composerKeyAction({ key: e.key, shiftKey: e.shiftKey, isComposing: e.nativeEvent.isComposing, keyCode: e.keyCode }) === 'send') {
              e.preventDefault();
              submit();
            }
          }}
        />
        <div className={styles.bar}>
          {/* The mode as a segmented control: native radios (arrow keys move and select), one group, labelled and explained. */}
          <div role="radiogroup" aria-label={tm('label')} aria-describedby="chat-mode-hint" aria-disabled={running || undefined} className={styles.modes}>
            {MODES.map((m) => (
              <label key={m} className={styles.modeOption}>
                <input
                  type="radio"
                  name="chat-mode"
                  value={m}
                  checked={mode === m}
                  className={styles.modeInput}
                  onClick={(e) => {
                    if (running) e.preventDefault();
                  }}
                  onKeyDown={(e) => {
                    if (running && e.key !== 'Tab') e.preventDefault();
                  }}
                  onChange={() => {
                    if (!running) onMode(m);
                  }}
                />
                <span>{tm(`${m}.name`)}</span>
              </label>
            ))}
          </div>
          <span className={styles.barEnd}>
            {text.length >= COUNT_FROM ? <span className={styles.count}>{t('count', { used: text.length, max: MAX_MESSAGE_LENGTH })}</span> : null}
            {running ? (
              <Button variant="secondary" size="sm" className={styles.sendButton} onClick={onCancel}>
                <Icon name="stop" />
                <VisuallyHidden>{t('cancel')}</VisuallyHidden>
              </Button>
            ) : (
              <Button type="submit" size="sm" className={styles.sendButton} disabled={!text.trim()}>
                <Icon name="arrowUp" />
                <VisuallyHidden>{t('send')}</VisuallyHidden>
              </Button>
            )}
          </span>
        </div>
      </div>
      <p className={styles.hint}>
        <span id="chat-mode-description">{tm(`${mode}.description`)}</span>
        <span id="chat-input-hint" className={styles.keyHint}>
          {t('hint')}
        </span>
        <VisuallyHidden id="chat-mode-hint">{tm('hint')}</VisuallyHidden>
      </p>
    </form>
  );
});
