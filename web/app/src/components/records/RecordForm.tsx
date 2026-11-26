'use client';

import { useState, type FormEvent, type ReactNode } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { Alert, Badge, Button, Card, Checkbox, Icon, Select, Table, TextField, type TableColumn } from '../../ui';
import { toolFor, usable } from '../../records/access';
import { executable, summarizeChanges, type ActionModel } from '../../records/actions';
import { buildActivity, buildLines, groupDigits, splitTotals, type LinesModel, type TotalLine } from '../../records/detailModel';
import { buildFormModel, type FormField } from '../../records/formModel';
import { pick } from '../../records/labels';
import { submitAction, type SubmitResult } from '../../records/submitAction';
import type { Caller, RecordsData } from '../../records/types';
import { CellView, MoneyText, keep } from './Cells';
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

function Lines({ lines, totals, emptyText, totalsLabel }: { lines: LinesModel; totals: ReadonlyArray<TotalLine>; emptyText: string; totalsLabel: string }) {
  type Row = { key: string; cells: LinesModel['rows'][number]['cells'] };
  const columns: TableColumn<Row>[] = lines.columns.map((c, i) => ({
    key: c.id, header: c.label, numeric: c.numeric, rowHeader: i === 0,
    render: (r) => <CellView cell={r.cells.find((x) => x.columnId === c.id)} />,
  }));
  return (
    <Card as="section" aria-labelledby={`lines-${lines.id}`} className={styles.section}>
      <h2 id={`lines-${lines.id}`} className={styles.sectionTitle}>{lines.title}</h2>
      <Table className={styles.linesTable} caption={lines.title} captionHidden columns={columns} rows={lines.rows as Row[]} rowKey={(r) => r.key}
        empty={<p className={styles.emptyLine}>{emptyText}</p>} />
      {lines.rows.length ? <LineCards lines={lines} /> : null}
      {totals.length ? <Totals totals={totals} label={totalsLabel} /> : null}
    </Card>
  );
}

/** Phones: each line as a row with its first column as the title, the middle columns as a caption and the last amount at the end. */
function LineCards({ lines }: { lines: LinesModel }) {
  const [head, ...rest] = lines.columns;
  const amount = [...rest].reverse().find((c) => c.kind === 'money');
  const middle = rest.filter((c) => c !== amount);
  return (
    <ul className={styles.lineCards} data-layout="cards">
      {lines.rows.map((r) => {
        const cell = (id?: string) => r.cells.find((x) => x.columnId === id);
        return (
          <li key={r.key} className={styles.lineCard}>
            <span className={styles.cardMeta}>
              <span className={styles.cardId}><CellView cell={cell(head?.id)} /></span>
              <span className={styles.lineCaption}>
                {middle.map((c) => (
                  <span key={c.id}>{c.label} <CellView cell={cell(c.id)} /></span>
                ))}
              </span>
            </span>
            {amount ? <span className={styles.cardAmount}><CellView cell={cell(amount.id)} /></span> : null}
          </li>
        );
      })}
    </ul>
  );
}

function Totals({ totals, label }: { totals: ReadonlyArray<TotalLine>; label: string }) {
  return (
    <dl className={styles.totals} aria-label={label}>
      {totals.map((x) => (
        <div key={x.id} className={styles.totalRow} data-grand={x.grand ? 'true' : undefined}>
          <dt>{x.label}</dt>
          <dd>{x.value ? <MoneyText money={{ value: x.value, currency: x.currency }} /> : '—'}</dd>
        </div>
      ))}
    </dl>
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

  const entity = data.entities.find((e) => e.id === entityId)!;
  const plural = pick(entity.pluralLabels, locale, entityId);
  const { fields, totals } = splitTotals(data, model);
  const lines = buildLines(data, entityId, caller, locale, recordId);
  const activity = recordId ? buildActivity(data, entityId, caller, locale, recordId) : null;
  const when = new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short', numberingSystem: 'latn', calendar: 'gregory', timeZone: 'UTC' } as Intl.DateTimeFormatOptions);

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
  const button = (a: ActionModel) =>
    executable(a) ? (
      <Button key={a.id} variant={a.kind === 'cancel' ? 'danger' : 'secondary'} onClick={() => run(a)} loading={busy}>{label(a)}</Button>
    ) : (
      <span key={a.id} className={styles.gated}>
        <Button variant="secondary" disabled>{label(a)}</Button> <Badge tone="warning">{ta('needsApproval')}</Badge>
      </span>
    );
  const onSubmit = (e: FormEvent) => { e.preventDefault(); if (model.saveAction) run(model.saveAction); };
  const saveLabel = model.saveAction ? label(model.saveAction) : '';
  const pendingChanges = pending
    ? summarizeChanges(writable, initial, values).map((c) => ({ ...c, label: model.fields.find((f) => f.id === c.fieldId)?.label ?? c.fieldId }))
    : [];
  // Cancel first (start side), then the other actions, the save last (end side) as the one primary button.
  const ordered = [...model.actions.filter((a) => a.kind === 'cancel'), ...model.actions.filter((a) => a.kind !== 'cancel')];

  /** A read-only value as text: option labels, linked names (a link only if the caller may open it), amounts and dates left-to-right. */
  const readValue = (f: FormField): ReactNode => {
    const v = values[f.id] ?? '';
    if (!v) return <span className={styles.none}>—</span>;
    const def = entity.fields.find((x) => x.id === f.id);
    if (def?.type === 'link' && def.target) {
      const target = data.entities.find((e) => e.id === def.target);
      const nameField = target?.fields.find((x) => x.type === 'string');
      const may = usable(toolFor(data.tools, def.target, 'get'), caller);
      const name = may && nameField ? data.rows[def.target]?.find((r) => r.id === v)?.[nameField.id] : undefined;
      const text = typeof name === 'string' && name ? name : v;
      return may ? <a className={styles.cellLink} href={`/records/${def.target}/${v}/`}>{text}</a> : text;
    }
    if (f.control === 'select') return f.options?.find((o) => o.value === v)?.label ?? v;
    if (f.control === 'boolean') return v === 'true' ? t('yes') : t('no');
    if (f.suffix) return <MoneyText money={{ value: v, currency: f.suffix }} />;
    if (f.control === 'numeric') return <bdi dir="ltr" className={styles.num}>{def?.type === 'phone' ? v : groupDigits(v)}</bdi>;
    if (f.control === 'date') return <bdi dir="ltr" className={styles.num}>{v}</bdi>;
    return <bdi>{v}</bdi>;
  };

  return (
    <div className={styles.screen}>
      <a className={styles.back} href={`/records/${entityId}/`}><Icon name="back" />{plural}</a>
      <header className={styles.recordHead}>
        <div className={styles.headText}>
          {model.recordId ? <p className={styles.eyebrow}>{model.title}</p> : null}
          <div className={styles.titleRow}>
            <h1 className={styles.title}>{model.recordId ? keep(model.recordId) : t('titleNew', { entity: model.title })}</h1>
            {model.stateLabel ? <StatusBadge label={model.stateLabel} tone={model.stateTone} /> : null}
          </div>
        </div>
        <div className={styles.headActions} role="group" aria-label={t('actionsLabel')}>
          {ordered.map(button)}
          {model.saveAction ? (
            executable(model.saveAction) ? <Button type="submit" form="record-form" loading={busy}>{saveLabel}</Button> : button(model.saveAction)
          ) : null}
        </div>
      </header>

      {model.mode === 'view' ? <p className={styles.note}><Icon name="lock" />{t('readOnly')}</p> : null}
      {result ? <Alert tone={result.status === 'refused' ? 'warning' : 'info'}>{t(`result.${result.status}`)}</Alert> : null}

      <div className={styles.detailGrid}>
        <div className={styles.detailMain}>
          <Card as="section" aria-labelledby="record-details" className={styles.section}>
            <h2 id="record-details" className={styles.sectionTitle}>{t('details')}</h2>
            <form id="record-form" onSubmit={onSubmit} className={styles.fieldGrid}>
              {fields.map((f) =>
                f.readOnly ? (
                  <div key={f.id} className={styles.readField}>
                    <span className={styles.readLabel}>{f.label}</span>
                    <span className={styles.readValue}>{readValue(f)}</span>
                  </div>
                ) : (
                  <Control key={f.id} f={f} value={values[f.id] ?? ''} onChange={(v) => setValues({ ...values, [f.id]: v })} t={t} />
                ),
              )}
            </form>
          </Card>
          {lines.map((l, i) => (
            <Lines key={l.id} lines={l} totals={i === lines.length - 1 ? totals : []} emptyText={t('linesEmpty')} totalsLabel={t('totals')} />
          ))}
          {lines.length === 0 && totals.length ? (
            <Card as="section" aria-label={t('totals')} className={styles.section}><Totals totals={totals} label={t('totals')} /></Card>
          ) : null}
        </div>
        {activity ? (
          <aside className={styles.detailSide} aria-labelledby="record-activity">
            <Card className={styles.section}>
              <h2 id="record-activity" className={styles.sectionTitle}><Icon name="history" />{t('activity')}</h2>
              {activity.length ? (
                <ol className={styles.timeline}>
                  {activity.map((a) => (
                    <li key={a.key} className={styles.event}>
                      <span className={styles.eventText}>
                        {t(`event.${a.event}`, { name: a.by })}
                        {a.stateLabel ? <> <StatusBadge label={a.stateLabel} tone={a.tone} /></> : null}
                      </span>
                      <time dateTime={a.at} className={styles.eventTime}>{when.format(new Date(a.at))}</time>
                    </li>
                  ))}
                </ol>
              ) : (
                <p className={styles.caption}>{t('activityEmpty')}</p>
              )}
            </Card>
          </aside>
        ) : null}
      </div>

      {pending ? (
        <ConfirmWrite actionLabel={label(pending)} entityLabel={model.title} recordId={model.recordId} risk={pending.risk}
          changes={pendingChanges} sensitive={pending.effects.ledger || pending.effects.tax || pending.effects.externalSend}
          busy={busy} onConfirm={() => void send(pending)} onCancel={() => setPending(null)} />
      ) : null}
    </div>
  );
}
