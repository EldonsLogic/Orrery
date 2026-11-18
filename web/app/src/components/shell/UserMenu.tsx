'use client';

import { useEffect, useId, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Badge, Button } from '../../ui';
import { locales, isLocale } from '../../i18n';
import { useTheme } from '../../lib/useTheme';
import { useSettings } from '../Providers';
import type { SessionClaims } from '../../lib/session';
import { useSession } from './SessionProvider';
import styles from './Shell.module.css';

const MODES = ['system', 'light', 'dark'] as const;

/** Disclosure panel (not an ARIA menu, so ordinary Tab order works): language, theme, MFA badge, sign-out. Escape closes and returns focus. */
export function UserMenu({ displayName, claims }: { displayName: string; claims: SessionClaims }) {
  const t = useTranslations('shell.user');
  const { locale, setLocale } = useSettings();
  const { mode, setMode } = useTheme();
  const { signOut } = useSession();
  const [open, setOpen] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const root = useRef<HTMLDivElement>(null);
  const panelId = useId();

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setOpen(false);
        trigger.current?.focus();
      }
    };
    const onDown = (e: MouseEvent) => {
      if (root.current && !root.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('keydown', onKey);
    document.addEventListener('mousedown', onDown);
    return () => {
      document.removeEventListener('keydown', onKey);
      document.removeEventListener('mousedown', onDown);
    };
  }, [open]);

  const doSignOut = async () => {
    await signOut();
    window.location.assign('/login/');
  };

  return (
    <div className={styles.userMenu} ref={root}>
      <button
        ref={trigger}
        type="button"
        className={styles.userButton}
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((v) => !v)}
      >
        {t('open', { name: displayName })}
      </button>
      {open ? (
        <div id={panelId} role="group" aria-label={t('panel')} className={styles.panel}>
          <p className={styles.panelName}>{displayName}</p>
          {/* Placeholder: the real state comes from the MFA claim of the token. */}
          <Badge tone={claims.mfaSatisfied ? 'success' : 'warning'}>{claims.mfaSatisfied ? t('mfaOn') : t('mfaOff')}</Badge>
          <label className={styles.field}>
            <span>{t('language')}</span>
            <select className={styles.select} value={locale} onChange={(e) => isLocale(e.target.value) && setLocale(e.target.value)}>
              {locales.map((l) => (
                <option key={l} value={l}>
                  {t(`languageName.${l}`)}
                </option>
              ))}
            </select>
          </label>
          <label className={styles.field}>
            <span>{t('theme')}</span>
            <select className={styles.select} value={mode} onChange={(e) => setMode(e.target.value as (typeof MODES)[number])}>
              {MODES.map((m) => (
                <option key={m} value={m}>
                  {t(`themeName.${m}`)}
                </option>
              ))}
            </select>
          </label>
          <Button variant="secondary" onClick={() => void doSignOut()}>
            {t('signOut')}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
