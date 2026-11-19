'use client';

import { useLocale, useTranslations } from 'next-intl';
import { Alert } from '../../ui';
import { buildNav } from '../../lib/navigation';
import { callerOf } from '../../lib/session';
import { fixtureData } from '../../records/fixture/rows';
import { useSession } from './SessionProvider';
import Link from 'next/link';
import styles from './Shell.module.css';

/** Workspace home: links to what the caller may open, or an empty state when the roles open nothing. */
export function HomeView() {
  const t = useTranslations('shell.home');
  const locale = useLocale();
  const { session } = useSession();
  if (session.status !== 'ready') return null;
  const items = buildNav(fixtureData, callerOf(session.claims), locale, { home: '' }).flatMap((s) => (s.id === 'records' ? s.items : []));
  const current = session.memberships.find((m) => m.tenantId === session.claims.tenantId);
  return (
    <section aria-labelledby="home-title">
      <h1 id="home-title">{t('title', { workspace: current?.name ?? '' })}</h1>
      {items.length === 0 ? (
        <Alert tone="info" title={t('emptyTitle')}>
          {t('emptyBody')}
        </Alert>
      ) : (
        <>
          <p>{t('intro')}</p>
          <ul className={styles.homeList}>
            {items.map((i) => (
              <li key={i.id}>
                <Link className={styles.link} href={i.href}>
                  {i.label}
                </Link>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
