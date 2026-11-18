'use client';

import { useState, type FormEvent } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { Alert, Badge, Button, Checkbox, Select, Stack, TextField } from '../../ui';
import { executable, summarizeChanges, type ActionModel } from '../../records/actions';
import { buildFormModel, type FormField } from '../../records/formModel';
import { pick } from '../../records/labels';
import { submitAction, type SubmitResult } from '../../records/submitAction';
import type { Caller, RecordsData } from '../../records/types';
import { ConfirmWrite } from './ConfirmWrite';
import { StatusBadge } from './StatusBadge';
import styles from './Records.module.css';

export type RecordFormProps = { data: RecordsData; entityId: string; caller: Caller; recordId?: string };

function Control({ f, value, onChange, t }: { f: FormField; value: string; onChange: (v: string) => void; t: (k: string) => string }) {
  const common = { label: f.label, required: f.required, disabled: f.readOnly, requiredMark: f.required ? t('required') : undefined };
  if (f.control === 'boolean') return <Checkbox label={f.label} checked={value === 'true'} disabled={f.readOnly} onChange={(e) => onChange(String(e.target.checked))} />;
  if (f.control === 'select' || f.control === 'link') {
    return (
      <Select {...common} value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">{t('choose')}</option>
        {f.options?.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </Select>
    );
  }
  // Numbers, amounts, phones and dates stay left-to-right inside a right-to-left page.
  const ltr = f.control === 'numeric' || f.control === 'date';
  return (
    <TextField {...common} name={f.id} type={f.inputType} numeric={ltr} maxLength={f.maxLength} value={value}
      hint={f.suffix} onChange={(e) => onChange(e.target.value)} />
  );
}

export function RecordForm({ data, entityId, caller, recordId }: RecordFormProps) {
  const t = useTranslations('records.form');
  const ta = useTranslations('records.actions');
  const locale = useLocale();
  const model = buildFormModel(data, entityId, caller, locale, recordId);
  const initial = Object.fromEntries((model?.fields ?? []).map((f) => [f.id, f.value]));
  const [values, setValues] = useState<Record<string, string>>(initial);
  const [pending, setPending] = useState<ActionModel | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<SubmitResult | null>(null);
  if (!model) return <p role="alert">{t('noAccess')}</p>; // deny by default

  const label = (a: ActionModel) => pick(a.labels, locale, ta(a.kind));
  const writable = model.fields.filter((f) => !f.readOnly).map((f) => f.id);

  async function send(a: ActionModel) {
    setBusy(true);
    try {
      setResult(await submitAction({ entityId, recordId, action: a, values }));
    } catch {
      setResult({ status: 'refused' });
    } finally {
      setBusy(false);
      setPending(null);
    }
  }
  const run = (a: ActionModel) => {
    if (!executable(a)) return; // needs approval: never executed here
    if (a.mode === 'confirm') setPending(a);
    else void send(a);
  };
  const button = (a: ActionModel, variant: 'primary' | 'secondary' | 'danger' = 'secondary') =>
    executable(a) ? (
      <Button key={a.id} variant={a.kind === 'cancel' ? 'danger' : variant} onClick={() => run(a)} loading={busy}>{label(a)}</Button>
    ) : (
      <span key={a.id}>
        <Button variant="secondary" disabled>{label(a)}</Button> <Badge tone="warning">{ta('needsApproval')}</Badge>
      </span>
    );
  const onSubmit = (e: FormEvent) => { e.preventDefault(); if (model.saveAction) run(model.saveAction); };
  const saveLabel = model.saveAction ? label(model.saveAction) : '';
  const pendingChanges = pending
    ? summarizeChanges(writable, initial, values).map((c) => ({ ...c, label: model.fields.find((f) => f.id === c.fieldId)?.label ?? c.fieldId }))
    : [];

  return (
    <div>
      <div className={styles.head}>
        <h1 className={styles.title}>{model.recordId ? t('titleRecord', { entity: model.title, id: model.recordId }) : t('titleNew', { entity: model.title })}</h1>
        {model.stateLabel ? <StatusBadge label={model.stateLabel} tone={model.stateTone} /> : null}
      </div>
      {model.mode === 'view' ? <Alert tone="info">{t('readOnly')}</Alert> : null}
      {result ? (
        <Alert tone={result.status === 'refused' ? 'warning' : 'info'}>{t(`result.${result.status}`)}</Alert>
      ) : null}
      <form onSubmit={onSubmit}>
        <Stack gap={2}>
          {model.fields.map((f) => <Control key={f.id} f={f} value={values[f.id] ?? ''} onChange={(v) => setValues({ ...values, [f.id]: v })} t={t} />)}
          <Stack direction="row" gap={1} wrap align="center">
            {model.saveAction ? (executable(model.saveAction) ? <Button type="submit" loading={busy}>{saveLabel}</Button> : button(model.saveAction)) : null}
            {model.actions.map((a) => button(a))}
          </Stack>
        </Stack>
      </form>
      {pending ? (
        <ConfirmWrite actionLabel={label(pending)} entityLabel={model.title} recordId={model.recordId} risk={pending.risk}
          changes={pendingChanges} sensitive={pending.effects.ledger || pending.effects.tax || pending.effects.externalSend}
          busy={busy} onConfirm={() => void send(pending)} onCancel={() => setPending(null)} />
      ) : null}
    </div>
  );
}
