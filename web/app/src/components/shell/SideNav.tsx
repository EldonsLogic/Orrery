'use client';

import { useLocale, useTranslations } from 'next-intl';
import { usePathname } from 'next/navigation';
import Link from 'next/link';
import { buildNav } from '../../lib/navigation';
import { callerOf, type SessionClaims } from '../../lib/session';
import { canViewBlueprint } from '../../blueprint/access';
import { canEditBranding } from '../../settings/branding/access';
import { fixtureBlueprint } from '../../blueprint/fixture';
import { fixtureData } from '../../records/fixture/rows';
import styles from './Shell.module.css';

export function SideNav({ claims, onNavigate }: { claims: SessionClaims; onNavigate: () => void }) {
  const t = useTranslations('shell.nav');
  const locale = useLocale();
  const pathname = usePathname() ?? '';
  const caller = callerOf(claims);
  const sections = buildNav(fixtureData, caller, locale, { home: t('home') }).map((s) => {
    if (s.id !== 'workspace') return s;
    const extra = [{ id: 'chat', label: t('chat'), href: '/chat/' }];
    if (canViewBlueprint(fixtureBlueprint, caller)) extra.push({ id: 'blueprint', label: t('blueprint'), href: '/blueprint/' });
    if (canEditBranding(fixtureBlueprint, caller)) extra.push({ id: 'branding', label: t('branding'), href: '/settings/branding/' });
    return { ...s, items: [...s.items, ...extra] };
  });
  const hasRecords = sections.some((s) => s.id === 'records');
  return (
    <nav aria-label={t('label')} className={styles.nav}>
      {sections.map((s) => (
        <section key={s.id} aria-labelledby={`nav-${s.id}`} className={styles.navSection}>
          <h2 id={`nav-${s.id}`} className={styles.navHeading}>
            {t(`sections.${s.id}`)}
          </h2>
          <ul className={styles.navList}>
            {s.items.map((i) => {
              const current = pathname.startsWith(i.href);
              return (
                <li key={i.id}>
                  <Link href={i.href} className={styles.navLink} aria-current={current ? 'page' : undefined} onClick={onNavigate}>
                    {i.label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </section>
      ))}
      {hasRecords ? null : <p className={styles.navEmpty}>{t('empty')}</p>}
    </nav>
  );
}
