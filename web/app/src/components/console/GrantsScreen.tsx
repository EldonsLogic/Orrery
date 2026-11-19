'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { Alert, Badge, Button, Checkbox, Select, Table, TextField } from '../../ui';
import { can } from '../../console/access';
import {
  buildGrantsScreen,
  formatClock,
  formatUtc,
  SCOPE_OPTIONS,
  validateRequest,
  type GrantRow,
  type RequestError,
} from '../../console/grants';
import type { PortResult } from '../../console/port';
import { MAX_REASON_LEN, MAX_SUPPORT_SECONDS } from '../../console/types';
import { useConsole } from './ConsoleProvider';
import { AuditGate } from './AuditGate';
import { useViewAudit } from './useViewAudit';
import styles from './Console.module.css';

type Notice = { tone: 'info' | 'danger'; text: string } | null;

export function GrantsScreen() {
  const t = useTranslations('console.grants');
  const tc = useTranslations('console');
  const { data, session, now, port } = useConsole();
  const [tenantId, setTenantId] = useState('');
  const [reason, setReason] = useState('');
  const [scope, setScope] = useState<string[]>([]);
  const [minutes, setMinutes] = useState('60');
  const [errors, setErrors] = useState<RequestError[]>([]);
  const [notice, setNotice] = useState<Notice>(null);
  const audit = useViewAudit('grants');
  if (session.status !== 'ready') return null;
  if (audit !== 'ok') return <AuditGate state={audit} />;

  const { roles, staffId } = session;
  const screen = buildGrantsScreen(data.grants, roles, staffId, now);
  const tenantName = (id: string) => data.tenants.find((x) => x.tenantId === id)?.name ?? id;

  const hand = async (fn: () => Promise<PortResult>) => {
    const r = await fn();
    setNotice({ tone: 'info', text: r.reason === 'not_wired' ? t('notWired') : '' });
  };
  const submit = () => {
    const draft = { tenantId, reason, scope, durationMinutes: Number(minutes) };
    const errs = validateRequest(draft, roles, staffId, data.tenants, data.grants, now);
    setErrors(errs);
    if (!errs.length) void hand(() => port.request(draft));
  };

  type Row = GrantRow;
  const cols = (kind: 'pending' | 'approved' | 'closed') => [
    { key: 'tenant', header: t('col.tenant'), rowHeader: true, render: (r: Row) => tenantName(r.grant.tenantId) },
    { key: 'staff', header: t('col.staff'), render: (r: Row) => <bdi dir="ltr">{r.grant.staffId}</bdi> },
    { key: 'scope', header: t('col.scope'), render: (r: Row) => r.grant.scope.map((s) => tc(`scope.${s}`)).join(', ') },
    { key: 'reason', header: t('col.reason'), render: (r: Row) => r.grant.reason },
    kind === 'approved'
      ? { key: 'left', header: t('col.timeLeft'), render: (r: Row) => <bdi dir="ltr" className={styles.countdown}>{formatClock(r.remaining)}</bdi> }
      : { key: 'when', header: t('col.requested'), render: (r: Row) => <bdi dir="ltr">{formatUtc(r.grant.requestedAt)}</bdi> },
    { key: 'state', header: t('col.state'), render: (r: Row) => <Badge tone={kind === 'approved' ? 'success' : 'neutral'}>{kind === 'pending' ? t('awaitingApproval') : t(`state.${r.state}`)}</Badge> },
  ];
  const section = (key: 'pending' | 'approved' | 'closed', list: GrantRow[]) => (
    <section className={styles.section} aria-labelledby={`g-${key}`}>
      <h2 id={`g-${key}`}>{t(`section.${key}`)}</h2>
      <div className={styles.tableWrap}>
        <Table<Row> caption={t(`section.${key}`)} captionHidden rows={list} rowKey={(r) => r.grant.grantId} empty={t('empty')} columns={cols(key)} />
      </div>
    </section>
  );

  return (
    <div className={styles.section}>
      <h1>{t('title')}</h1>
      <p>{t('intro')}</p>
      {notice ? (
        <Alert tone={notice.tone} title={t('notSentTitle')}>
          {notice.text}
        </Alert>
      ) : null}
      {can(roles, 'grants.request') ? (
        <form className={styles.section} aria-labelledby="g-new" onSubmit={(e) => { e.preventDefault(); submit(); }}>
          <h2 id="g-new">{t('newTitle')}</h2>
          <Select label={t('form.tenant')} value={tenantId} onChange={(e) => setTenantId(e.target.value)} error={errors.includes('tenant') ? t('error.tenant') : undefined}>
            <option value="">{t('form.choose')}</option>
            {data.tenants.filter((x) => x.status === 'active' || x.status === 'trial').map((x) => (
              <option key={x.tenantId} value={x.tenantId}>
                {x.name}
              </option>
            ))}
          </Select>
          <TextField label={t('form.reason')} hint={t('form.reasonHint', { max: MAX_REASON_LEN })} value={reason} onChange={(e) => setReason(e.target.value)} error={errors.includes('reason') ? t('error.reason') : undefined} />
          <fieldset className={styles.checks} aria-invalid={errors.includes('scope') || undefined} aria-describedby={errors.includes('scope') ? 'g-scope-err' : undefined}>
            <legend>{t('form.scope')}</legend>
            {SCOPE_OPTIONS.map((s) => (
              <Checkbox key={s} label={tc(`scope.${s}`)} checked={scope.includes(s)} onChange={(e) => setScope(e.target.checked ? [...scope, s] : scope.filter((x) => x !== s))} />
            ))}
            {errors.includes('scope') ? <span id="g-scope-err" role="alert">{t('error.scope')}</span> : null}
          </fieldset>
          <TextField label={t('form.duration')} hint={t('form.durationHint', { max: MAX_SUPPORT_SECONDS / 60 })} numeric value={minutes} onChange={(e) => setMinutes(e.target.value)} error={errors.includes('duration') ? t('error.duration') : undefined} />
          {errors.includes('cap') ? <Alert tone="danger">{t('error.cap')}</Alert> : null}
          {errors.includes('forbidden') ? <Alert tone="danger">{t('error.forbidden')}</Alert> : null}
          <div>
            <Button type="submit">{t('form.submit')}</Button>
          </div>
        </form>
      ) : null}
      {section('pending', screen.pending)}
      {section('approved', screen.approved)}
      {section('closed', screen.closed)}
    </div>
  );
}
