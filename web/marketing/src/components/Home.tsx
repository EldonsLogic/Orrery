'use client';

import { useLocale, useTranslations } from 'next-intl';
import styles from './Home.module.css';

export function Home() {
  const t = useTranslations('home');
  const locale = useLocale();
  return (
    <main className={styles.page}>
      <h1 className={styles.title}>
        <bdi>{t('title')}</bdi>
      </h1>
      <p>{t('tagline')}</p>
      <a className={styles.link} href={locale === 'ar' ? '/en/' : '/ar/'} lang={locale === 'ar' ? 'en' : 'ar'}>
        {t('switchLanguage')}
      </a>
    </main>
  );
}
