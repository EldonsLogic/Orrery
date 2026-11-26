'use client';

import type { ReactNode } from 'react';
import { useTranslations } from 'next-intl';
import { Icon, type IconName } from '../../ui';
import styles from './SettingsLayout.module.css';

/** The settings sections that exist today. A section appears here only once its page exists (no dead links). */
const SECTIONS: ReadonlyArray<{ id: 'branding'; href: string; icon: IconName }> = [{ id: 'branding', href: '/settings/branding/', icon: 'palette' }];

/** Settings (WEB-029): section navigation at the start side, the section's content beside it; stacked on phones. */
export function SettingsLayout({ active, children }: { active: (typeof SECTIONS)[number]['id']; children: ReactNode }) {
  const t = useTranslations('settings');
  return (
    <div className={styles.layout}>
      <nav aria-label={t('nav')} className={styles.nav}>
        <p className={styles.navTitle}>{t('title')}</p>
        <ul className={styles.navList}>
          {SECTIONS.map((s) => (
            <li key={s.id}>
              <a href={s.href} className={styles.navLink} aria-current={s.id === active ? 'page' : undefined}>
                <Icon name={s.icon} />
                {t(s.id)}
              </a>
            </li>
          ))}
        </ul>
      </nav>
      <div className={styles.content}>{children}</div>
    </div>
  );
}
