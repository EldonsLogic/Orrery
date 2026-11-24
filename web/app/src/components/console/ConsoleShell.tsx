'use client';

import type { ReactNode } from 'react';
import Link from 'next/link';
import { useTranslations } from 'next-intl';
import { Alert, Badge } from '../../ui';
import { canSeeAudit, canSeeGrants, can } from '../../console/access';
import { useSettings } from '../Providers';
import { GrantBanner } from './GrantBanner';
import { useConsole } from './ConsoleProvider';
import styles from './Console.module.css';

/** Staff back office frame: one main landmark, role-filtered navigation, the grant banner. Never rendered for a denied session beyond the reason. */
export function ConsoleShell({ children }: { children: ReactNode }) {
  const t = useTranslations('console');
  const { session } = useConsole();
  const { locale, setLocale } = useSettings();

  if (session.status !== 'ready') {
    return (
      <div className={styles.root}>
        <main id="main" tabIndex={-1} className={styles.main}>
          <Alert tone="danger" title={t('denied.title')}>
            <p>{t(`denied.reason.${session.reason}`)}</p>
          </Alert>
        </main>
      </div>
    );
  }
  const roles = session.roles;
  const links = [
    can(roles, 'tenants.view') ? { href: '/console/', key: 'tenants' } : null,
    canSeeGrants(roles) ? { href: '/console/grants/', key: 'grants' } : null,
    can(roles, 'factory.view') ? { href: '/console/components/', key: 'components' } : null,
    canSeeAudit(roles) ? { href: '/console/audit/', key: 'audit' } : null,
  ].filter((x): x is { href: string; key: string } => x !== null);

  return (
    <div className={styles.root}>
      <header className={styles.topBar}>
        <strong>{t('title')}</strong>
        <Badge tone="success">{t('session.mfa')}</Badge>
        <span className={styles.meta}>
          {t('session.roles')}: {roles.map((r) => t(`roles.${r}`)).join(', ')}
        </span>
        <span className={styles.meta}>
          {t('session.version')} <bdi dir="ltr">{session.sessionVersion}</bdi>
        </span>
        <label className={styles.lang}>
          <span>{t('language')}</span>
          <select value={locale} onChange={(e) => setLocale(e.target.value === 'ar' ? 'ar' : 'en')}>
            <option value="en">{t('languageName.en')}</option>
            <option value="ar">{t('languageName.ar')}</option>
          </select>
        </label>
      </header>
      <nav aria-label={t('nav.label')} className={styles.nav}>
        {links.map((l) => (
          <Link key={l.key} href={l.href}>
            {t(`nav.${l.key}`)}
          </Link>
        ))}
      </nav>
      <main id="main" tabIndex={-1} className={styles.main}>
        <GrantBanner />
        {children}
      </main>
    </div>
  );
}
