'use client';

import type { ReactNode } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { Alert, Badge, Icon, Mark, type IconName } from '../../ui';
import { canSeeAudit, canSeeGrants, can } from '../../console/access';
import { useSettings } from '../Providers';
import { GrantBanner } from './GrantBanner';
import { useConsole } from './ConsoleProvider';
import styles from './Console.module.css';

const trim = (p: string) => p.replace(/\/+$/, '');
/** The console home matches only itself; every other section also matches its sub-pages. */
export const isCurrentConsolePath = (href: string, pathname: string): boolean => {
  const h = trim(href);
  const p = trim(pathname);
  if (!p) return false;
  return h === '/console' ? p === h : p === h || p.startsWith(`${h}/`);
};

/**
 * Staff back office frame (WEB-029 design): a solid staff-realm strip on every page, denied or not, so a team member never
 * mistakes it for a tenant view; one main landmark, role-filtered navigation, the grant banner. A denied session sees the
 * reason only.
 */
export function ConsoleShell({ children }: { children: ReactNode }) {
  const t = useTranslations('console');
  const { session } = useConsole();
  const { locale, setLocale } = useSettings();
  const pathname = usePathname() ?? '';

  const realm = (
    <div className={styles.realm}>
      <Icon name="lock" />
      <strong className={styles.realmLabel}>{t('realm.label')}</strong>
      <span className={styles.realmNote}>{t('realm.note')}</span>
    </div>
  );

  if (session.status !== 'ready') {
    return (
      <div className={styles.root} data-realm="staff">
        {realm}
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
    can(roles, 'tenants.view') ? { href: '/console/', key: 'tenants', icon: 'users' } : null,
    canSeeGrants(roles) ? { href: '/console/grants/', key: 'grants', icon: 'lock' } : null,
    can(roles, 'factory.view') ? { href: '/console/components/', key: 'components', icon: 'package' } : null,
    canSeeAudit(roles) ? { href: '/console/audit/', key: 'audit', icon: 'history' } : null,
  ].filter((x): x is { href: string; key: string; icon: IconName } => x !== null);

  return (
    <div className={styles.root} data-realm="staff">
      {realm}
      <header className={styles.topBar}>
        <span className={styles.brand}>
          <Mark size={20} />
          <strong>{t('title')}</strong>
        </span>
        <div className={styles.sessionMeta}>
          <Badge tone="success" icon={<Icon name="statusDone" />}>
            {t('session.mfa')}
          </Badge>
          <span className={styles.meta}>
            {t('session.roles')}: {roles.map((r) => t(`roles.${r}`)).join(', ')}
          </span>
          <span className={styles.meta}>
            {t('session.version')} <bdi dir="ltr">{session.sessionVersion}</bdi>
          </span>
        </div>
        <label className={styles.lang}>
          <span className={styles.langLabel}>{t('language')}</span>
          <select className={styles.langSelect} value={locale} onChange={(e) => setLocale(e.target.value === 'ar' ? 'ar' : 'en')}>
            <option value="en">{t('languageName.en')}</option>
            <option value="ar">{t('languageName.ar')}</option>
          </select>
        </label>
      </header>
      <div className={styles.frame}>
        <nav aria-label={t('nav.label')} className={styles.nav}>
          {links.map((l) => (
            <Link key={l.key} href={l.href} className={styles.navLink} aria-current={isCurrentConsolePath(l.href, pathname) ? 'page' : undefined}>
              <Icon name={l.icon} />
              <span>{t(`nav.${l.key}`)}</span>
            </Link>
          ))}
        </nav>
        <main id="main" tabIndex={-1} className={styles.main}>
          <GrantBanner />
          {children}
        </main>
      </div>
    </div>
  );
}
