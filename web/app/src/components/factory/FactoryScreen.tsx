'use client';

import { useCallback, useEffect, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { Alert, Badge, Button, Select } from '../../ui';
import { useConsole } from '../console/ConsoleProvider';
import { AuditGate } from '../console/AuditGate';
import { useViewAudit } from '../console/useViewAudit';
import { can } from '../../console/access';
import { countByStatus, filterByStatus, statusTone } from '../../factory/model';
import { fixturePort, type FactoryReviewPort, type ListResult } from '../../factory/port';
import { plainText } from '../../factory/text';
import { REQUEST_STATUSES, type RequestStatus } from '../../factory/types';
import { RequestDetail } from './RequestDetail';
import { LoadingMark } from '../marks/LoadingMark';
import styles from './Factory.module.css';

/**
 * Component requests for staff to review (PLT-014). Read-only apart from four decisions that go to the injected port.
 * Shows nothing until the view audit resolved (like every console screen) and nothing for a session without the
 * factory view permission. The default port is the fixture port (no backend).
 */
export function FactoryScreen({ port = fixturePort }: { port?: FactoryReviewPort }) {
  const t = useTranslations('console.factory');
  const te = useTranslations('console.factory.errors');
  const locale = useLocale() === 'ar' ? 'ar' : 'en';
  const { session } = useConsole();
  const gate = useViewAudit('component_requests');
  const allowed = session.status === 'ready' && can(session.roles, 'factory.view');
  const [load, setLoad] = useState<'loading' | ListResult>('loading');
  const [status, setStatus] = useState<RequestStatus | ''>('');
  const [selected, setSelected] = useState<string | null>(null);

  const reload = useCallback(() => {
    let live = true;
    port
      .list()
      .then((r) => live && setLoad(r))
      .catch(() => live && setLoad({ ok: false, code: 'unavailable' }));
    return () => {
      live = false;
    };
  }, [port]);
  useEffect(() => {
    if (!allowed || gate !== 'ok') return;
    return reload();
  }, [allowed, gate, reload]);

  if (session.status !== 'ready') return null;
  if (!allowed) {
    return (
      <Alert tone="danger" title={t('noAccess.title')}>
        {t('noAccess.body')}
      </Alert>
    );
  }
  if (gate !== 'ok') return <AuditGate state={gate} />;

  const body = () => {
    if (load === 'loading') return <LoadingMark label={t('loading')} />;
    if (!load.ok)
      return (
        <Alert tone="danger" title={t('error.title')}>
          <p>{te.has(load.code) ? te(load.code) : te('other')}</p>
          <Button variant="secondary" onClick={() => { setLoad('loading'); reload(); }}>
            {t('error.retry')}
          </Button>
        </Alert>
      );
    const counts = countByStatus(load.requests);
    const rows = filterByStatus(load.requests, status);
    const open = load.requests.find((r) => r.id === selected) ?? null;
    return (
      <div className={styles.layout} data-selected={open ? 'true' : 'false'}>
        <div className={styles.listPane}>
          <Select label={t('filter.status')} value={status} onChange={(e) => setStatus(e.target.value as RequestStatus | '')}>
            <option value="">{t('filter.all', { n: load.requests.length })}</option>
            {REQUEST_STATUSES.map((s) => (
              <option key={s} value={s}>
                {t(`status.${s}`)} ({counts[s]})
              </option>
            ))}
          </Select>
          {rows.length === 0 ? (
            <p role="status">{t('list.empty')}</p>
          ) : (
            <ul className={styles.list} aria-label={t('list.caption')}>
              {rows.map((r) => (
                <li key={r.id}>
                  <button type="button" className={styles.item} aria-current={r.id === selected ? 'true' : undefined} onClick={() => setSelected(r.id)}>
                    <span className={styles.itemTop}>
                      <bdi dir="ltr">{plainText(r.id, 40)}</bdi>
                      <Badge tone={statusTone(r.status)}>{t.has(`status.${r.status}`) ? t(`status.${r.status}`) : plainText(r.status, 40)}</Badge>
                    </span>
                    <bdi dir="auto" className={styles.plain}>{plainText(r.need?.ref, 80)}</bdi>
                    <span className={styles.note}>{t('list.tenants', { n: Object.values(r.tenants ?? {}).filter((e) => Array.isArray(e) && e.length > 0).length })}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className={styles.detailPane}>
          {open ? (
            <>
              <Button variant="ghost" className={styles.back} onClick={() => setSelected(null)}>
                {t('detail.back')}
              </Button>
              <RequestDetail record={open} reviewer={{ staffId: session.staffId, roles: session.roles }} minTenants={load.minTenants} port={port} locale={locale} onDone={() => reload()} />
            </>
          ) : (
            <p className={styles.note}>{t('detail.pick')}</p>
          )}
        </div>
      </div>
    );
  };

  return (
    <section className={styles.screen} aria-labelledby="factory-h">
      <h1 id="factory-h">{t('title')}</h1>
      <p>{t('intro')}</p>
      <Alert tone="info">{t('serverNote')}</Alert>
      {body()}
    </section>
  );
}
