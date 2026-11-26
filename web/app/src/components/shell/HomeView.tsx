'use client';

import { useEffect, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { Alert } from '../../ui';
import { buildNav } from '../../lib/navigation';
import { callerOf } from '../../lib/session';
import { fixtureData } from '../../records/fixture/rows';
import { fixtureHomePort, type HomePort } from '../../home/port';
import type { HomeOverview } from '../../home/types';
import { HomeScreen } from '../home/HomeScreen';
import { useSession } from './SessionProvider';

/** Workspace home: the owner overview from the home port, or an empty state when the roles open nothing. */
export function HomeView({ port = fixtureHomePort }: { port?: HomePort }) {
  const t = useTranslations('shell.home');
  const locale = useLocale();
  const { session } = useSession();
  const [data, setData] = useState<HomeOverview | null | undefined>(undefined);
  const claims = session.status === 'ready' ? session.claims : null;

  useEffect(() => {
    if (!claims) return;
    let live = true;
    setData(undefined);
    port.overview(claims).then((o) => live && setData(o), () => live && setData(null));
    return () => {
      live = false;
    };
  }, [claims, port]);

  if (session.status !== 'ready') return null;
  const items = buildNav(fixtureData, callerOf(session.claims), locale, { home: '' }).flatMap((s) => (s.id === 'records' ? s.items : []));
  const current = session.memberships.find((m) => m.tenantId === session.claims.tenantId);
  if (items.length === 0) {
    return (
      <section aria-labelledby="home-title">
        <h1 id="home-title">{t('title', { workspace: current?.name ?? '' })}</h1>
        <Alert tone="info" title={t('emptyTitle')}>
          {t('emptyBody')}
        </Alert>
      </section>
    );
  }
  // While loading (and when the port has no overview) the header, Ask Seshna and the record shortcuts still show.
  return <HomeScreen data={data ?? null} loading={data === undefined} company={current?.name ?? ''} person={session.displayName} shortcuts={items} />;
}
