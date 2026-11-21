'use client';

import { useState, type ReactNode } from 'react';
import { useTranslations } from 'next-intl';
import { Alert, Button, Select } from '../../ui';
import { actionState, type ActionState, type Reviewer } from '../../factory/model';
import type { FactoryReviewPort } from '../../factory/port';
import {
  REJECT_REASONS,
  RISK_CLASSES,
  type ComponentRequestRecord,
  type RejectReason,
  type ReviewAction,
  type ReviewCommand,
  type RiskClass,
} from '../../factory/types';
import styles from './Factory.module.css';

type Props = {
  record: ComponentRequestRecord;
  reviewer: Reviewer;
  minTenants: number;
  port: FactoryReviewPort;
  /** Called after the server accepted a decision, so the list is read again. */
  onDone: () => void;
};

/**
 * attest, approve, reject. Every button only calls the injected port. A button is off, with its reason written next to it,
 * unless this staff user may act. That is a guide: the SERVER enforces the reviewer role, separation of duties, the
 * money-field rule and MFA step-up, and can still refuse an enabled button (the answer is shown).
 */
export function ReviewActions({ record, reviewer, minTenants, port, onDone }: Props) {
  const t = useTranslations('console.factory.actions');
  const ts = useTranslations('console.factory.stepUp');
  const te = useTranslations('console.factory.errors');
  const [riskClass, setRiskClass] = useState<RiskClass>('plain');
  const [reason, setReason] = useState<RejectReason>('not_generalisable');
  const [pending, setPending] = useState<ReviewCommand | null>(null);
  const [busy, setBusy] = useState(false);
  const [outcome, setOutcome] = useState<'done' | string | null>(null);

  const state = (a: ReviewAction): ActionState => actionState(record, reviewer, a, minTenants, a === 'attest_risk_class' ? riskClass : undefined);
  const ask = (action: ReviewAction) => {
    setOutcome(null);
    setPending({ requestId: record.id, action, ...(action === 'attest_risk_class' ? { riskClass } : {}), ...(action === 'reject' ? { reason } : {}) });
  };
  const confirm = async () => {
    if (!pending || busy) return;
    setBusy(true);
    let code: string | null = null;
    try {
      const res = await port.act(pending);
      code = res.ok ? null : String(res.code);
    } catch {
      code = 'unavailable';
    }
    setBusy(false);
    setPending(null);
    if (code === null) {
      setOutcome('done');
      onDone();
    } else setOutcome(code);
  };

  const row = (action: ReviewAction, label: string, variant: 'primary' | 'secondary' | 'danger', extra?: ReactNode) => {
    const s = state(action);
    const id = `why-${record.id}-${action}`;
    return (
      <div className={styles.action}>
        {extra}
        <Button variant={variant} disabled={!s.enabled || pending !== null} aria-describedby={s.enabled ? undefined : id} onClick={() => ask(action)}>
          {label}
        </Button>
        {s.enabled ? null : (
          <p id={id} className={styles.why}>
            {t(`why.${s.reason}`)}
          </p>
        )}
      </div>
    );
  };

  return (
    <section className={styles.block} aria-labelledby={`act-${record.id}`}>
      <h2 id={`act-${record.id}`}>{t('title')}</h2>
      <p>{t('note')}</p>
      {row(
        'attest_risk_class',
        t('attestRisk'),
        'secondary',
        <Select label={t('riskClass')} value={riskClass} onChange={(e) => setRiskClass(e.target.value as RiskClass)}>
          {RISK_CLASSES.map((c) => (
            <option key={c} value={c}>
              {t(`riskClasses.${c}`)}
            </option>
          ))}
        </Select>,
      )}
      {row('attest_generalisable', t('attestGen'), 'secondary')}
      {row('approve', t('approve'), 'primary')}
      {row(
        'reject',
        t('reject'),
        'danger',
        <Select label={t('rejectReason')} value={reason} onChange={(e) => setReason(e.target.value as RejectReason)}>
          {REJECT_REASONS.map((r) => (
            <option key={r} value={r}>
              {t(`rejectReasons.${r}`)}
            </option>
          ))}
        </Select>,
      )}
      {pending ? (
        <Alert tone="warning" title={ts('title')} data-testid="step-up">
          <p>{ts('body')}</p>
          <div className={styles.buttons}>
            <Button loading={busy} onClick={() => void confirm()}>
              {ts('confirm')}
            </Button>
            <Button variant="ghost" disabled={busy} onClick={() => setPending(null)}>
              {ts('cancel')}
            </Button>
          </div>
        </Alert>
      ) : null}
      {outcome === 'done' ? <Alert tone="success">{t('done')}</Alert> : null}
      {outcome && outcome !== 'done' ? (
        <Alert tone="danger" title={t('refusedTitle')}>
          {te.has(outcome) ? te(outcome) : te('other')}
        </Alert>
      ) : null}
    </section>
  );
}
