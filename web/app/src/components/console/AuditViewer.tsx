'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { Badge, Select, Table } from '../../ui';
import { buildAuditView, distinct } from '../../console/audit';
import { formatUtc } from '../../console/grants';
import type { AuditEntry } from '../../console/types';
import { useConsole } from './ConsoleProvider';
import { AuditGate } from './AuditGate';
import { useViewAudit } from './useViewAudit';
import styles from './Console.module.css';

/** Grant and access events, read only. Support sees its own entries; wider roles see all. */
export function AuditViewer() {
  const t = useTranslations('console.audit');
  const { data, session } = useConsole();
  const [tenant, setTenant] = useState('');
  const [actor, setActor] = useState('');
  const [action, setAction] = useState('');
  const gate = useViewAudit('audit');
  if (session.status !== 'ready') return null;
  if (gate !== 'ok') return <AuditGate state={gate} />;

  const visible = buildAuditView(data.audit, session.roles, session.staffId);
  const rows = buildAuditView(data.audit, session.roles, session.staffId, { tenant, actor, action });
  const opts = (vals: string[], label: (v: string) => string) =>
    vals.map((v) => (
      <option key={v} value={v}>
        {label(v)}
      </option>
    ));
  const tenantName = (id: string) => data.tenants.find((x) => x.tenantId === id)?.name ?? id;
  return (
    <section className={styles.section} aria-labelledby="audit-h">
      <h1 id="audit-h">{t('title')}</h1>
      <p>{t('intro')}</p>
      <div className={styles.filters}>
        <Select label={t('tenant')} value={tenant} onChange={(e) => setTenant(e.target.value)}>
          <option value="">{t('any')}</option>
          {opts(distinct(visible.map((e) => e.tenant)), tenantName)}
        </Select>
        <Select label={t('actor')} value={actor} onChange={(e) => setActor(e.target.value)}>
          <option value="">{t('any')}</option>
          {opts(distinct(visible.map((e) => e.subject)), (v) => v)}
        </Select>
        <Select label={t('action')} value={action} onChange={(e) => setAction(e.target.value)}>
          <option value="">{t('any')}</option>
          {opts(distinct(visible.map((e) => e.action)), (v) => t(`actions.${v}`))}
        </Select>
      </div>
      <div className={styles.tableWrap}>
        <Table<AuditEntry & Record<string, unknown>>
          caption={t('caption')}
          rows={rows}
          rowKey={(e) => e.seq}
          empty={t('empty')}
          columns={[
            { key: 'at', header: t('col.at'), rowHeader: true, render: (e) => <bdi dir="ltr">{formatUtc(e.at)}</bdi> },
            { key: 'action', header: t('col.action'), render: (e) => t(`actions.${e.action}`) },
            { key: 'decision', header: t('col.decision'), render: (e) => <Badge tone={e.decision === 'allow' ? 'success' : 'danger'}>{t(`decision.${e.decision}`)}</Badge> },
            { key: 'actor', header: t('col.actor'), render: (e) => <bdi dir="ltr">{e.subject ?? '-'}</bdi> },
            { key: 'tenant', header: t('col.tenant'), render: (e) => (e.tenant ? tenantName(e.tenant) : '-') },
            { key: 'code', header: t('col.code'), render: (e) => <bdi dir="ltr">{e.code}</bdi> },
          ]}
        />
      </div>
    </section>
  );
}
