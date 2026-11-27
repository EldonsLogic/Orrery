'use client';

import { useTranslations } from 'next-intl';
import { locales } from '../../i18n';
import { useSettings } from '../Providers';
import styles from './Shell.module.css';

/** Visible language switch (عربي / English): flips locale and direction live; Providers remembers the choice per viewer. Arabic stays the default. */
export function LanguageSwitch() {
  const t = useTranslations('shell.language');
  const { locale, setLocale } = useSettings();
  return (
    <div role="group" aria-label={t('label')} className={styles.lang}>
      {locales.map((l) => (
        <button
          key={l}
          type="button"
          lang={l}
          dir={l === 'ar' ? 'rtl' : 'ltr'}
          className={styles.langButton}
          aria-pressed={locale === l}
          onClick={() => setLocale(l)}
        >
          {t(l)}
        </button>
      ))}
    </div>
  );
}
