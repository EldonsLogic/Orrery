'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { Button, Select } from '../../ui';
import { composerKeyAction } from '../../chat/text';
import { MAX_MESSAGE_LENGTH, MODES, type ChatMode } from '../../chat/types';
import styles from './Chat.module.css';

export type ComposerProps = {
  mode: ChatMode;
  running: boolean;
  onMode: (m: ChatMode) => void;
  onSend: (text: string) => boolean;
  onCancel: () => void;
};

export function Composer({ mode, running, onMode, onSend, onCancel }: ComposerProps) {
  const t = useTranslations('chat.composer');
  const tm = useTranslations('chat.mode');
  const [text, setText] = useState('');
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
      <label htmlFor="chat-input" className={styles.meta}>{t('label')}</label>
      <textarea
        id="chat-input"
        className={styles.textarea}
        dir="auto"
        rows={3}
        value={text}
        maxLength={MAX_MESSAGE_LENGTH}
        readOnly={running}
        aria-disabled={running || undefined}
        placeholder={t('placeholder')}
        aria-describedby="chat-input-hint"
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (composerKeyAction({ key: e.key, shiftKey: e.shiftKey, isComposing: e.nativeEvent.isComposing, keyCode: e.keyCode }) === 'send') {
            e.preventDefault();
            submit();
          }
        }}
      />
      <p id="chat-input-hint" className={styles.hint}>{t('hint')}</p>
      <div className={styles.bar}>
        <Select
          label={tm('label')}
          hint={tm('hint')}
          value={mode}
          aria-disabled={running || undefined}
          onChange={(e) => {
            if (!running) onMode(e.target.value as ChatMode);
          }}
        >
          {MODES.map((m) => (
            <option key={m} value={m}>{tm(`${m}.name`)}</option>
          ))}
        </Select>
        <span className={styles.count}>{t('count', { used: text.length, max: MAX_MESSAGE_LENGTH })}</span>
        {running ? (
          <Button variant="secondary" onClick={onCancel}>{t('cancel')}</Button>
        ) : (
          <Button type="submit" disabled={!text.trim()}>{t('send')}</Button>
        )}
      </div>
      <p className={styles.hint}>{tm(`${mode}.description`)}</p>
    </form>
  );
}
