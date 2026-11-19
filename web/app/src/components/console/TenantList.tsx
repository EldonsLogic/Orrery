'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { Alert, Badge, Button, Select, Table, TextField, type BadgeTone } from '../../ui';
import { liveGrantFor } from '../../console/grants';
import { buildTenantList, regionsOf } from '../../console/tenants';
import type { TenantHealth, TenantMeta, TenantStatus } from '../../console/types';
import { useConsole } from './ConsoleProvider';
import { useViewAudit } from './useViewAudit';
import styles from './Console.module.css';

const STATUSES: TenantStatus[] = ['trial', 'active', 'suspended', 'exported', 'deleted'];
const HEALTHS: TenantHealth[] = ['healthy', 'degraded', 'down', 'unknown'];
const healthTone = (h: TenantHealth): BadgeTone => (h === 'healthy' ? 'success' : h === 'degraded' ? 'warning' : h === 'down' ? 'danger' : 'neutral');

/** Metadata only (plan, status, region, health). No customer data is on this screen or behind it without an approved grant. */
export function TenantList() {
  const t = useTranslations('console.tenants');
  const tc = useTranslations('console');
  const { data, session, now, enterTenant, activeTenantId } = useConsole();
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState<TenantStatus | ''>('');
  const [region, setRegion] = useState('');
  const [health, setHealth] = useState<TenantHealth | ''>('');
  const [refused, setRefused] = useState(false);
  useViewAudit('tenants');
  if (session.status !== 'ready') return null;

  const rows = buildTenantList(data.tenants, session.roles, { query, status, region, health });
  return (
    <section className={styles.section} aria-labelledby="tenants-h">
      <h1 id="tenants-h">{t('title')}</h1>
      <p>{t('intro')}</p>
      <div className={styles.filters}>
        <TextField label={t('search')} type="search" value={query} onChange={(e) => setQuery(e.target.value)} />
        <Select label={t('status')} value={status} onChange={(e) => setStatus(e.target.value as TenantStatus | '')}>
          <option value="">{t('any')}</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {tc(`tenantStatus.${s}`)}
            </option>
          ))}
        </Select>
        <Select label={t('region')} value={region} onChange={(e) => setRegion(e.target.value)}>
          <option value="">{t('any')}</option>
          {regionsOf(data.tenants).map((r) => (
            <option key={r} value={r}>
              {tc(`regions.${r}`)}
            </option>
          ))}
        </Select>
        <Select label={t('health')} value={health} onChange={(e) => setHealth(e.target.value as TenantHealth | '')}>
          <option value="">{t('any')}</option>
          {HEALTHS.map((h) => (
            <option key={h} value={h}>
              {tc(`health.${h}`)}
            </option>
          ))}
        </Select>
      </div>
      {refused ? (
        <Alert tone="danger" title={t('refusedTitle')}>
          {t('refusedBody')}
        </Alert>
      ) : null}
      <div className={styles.tableWrap}>
        <Table<TenantMeta & Record<string, unknown>>
          caption={t('caption')}
          rows={rows}
          rowKey={(r) => r.tenantId}
          empty={t('empty')}
          columns={[
            { key: 'name', header: t('col.name'), rowHeader: true },
            { key: 'plan', header: t('col.plan'), render: (r) => r.plan },
            { key: 'status', header: t('col.status'), render: (r) => tc(`tenantStatus.${r.status}`) },
            { key: 'region', header: t('col.region'), render: (r) => tc(`regions.${r.region}`) },
            { key: 'health', header: t('col.health'), render: (r) => <Badge tone={healthTone(r.health)}>{tc(`health.${r.health}`)}</Badge> },
            {
              key: 'access',
              header: t('col.access'),
              render: (r) =>
                liveGrantFor(data.grants, session.staffId, r.tenantId, now) ? (
                  <Button
                    size="sm"
                    variant="secondary"
                    disabled={activeTenantId === r.tenantId}
                    onClick={() => setRefused(!enterTenant(r.tenantId))}
                  >
                    {t('enter')}
                  </Button>
                ) : (
                  t('noGrant')
                ),
            },
          ]}
        />
      </div>
    </section>
  );
}
