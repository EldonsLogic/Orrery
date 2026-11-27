'use client';

import { useId, useState, type ChangeEvent, type DragEvent } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { Alert, Badge, Button, Card, Icon, Table, VisuallyHidden, type TableColumn } from '../../ui';
import { cx } from '../../ui/cx';
import button from '../../ui/Button.module.css';
import { parseCsv } from '../../records/csv';
import {
  MAX_IMPORT_BYTES, MAX_IMPORT_ROWS, autoMap, buildImportPlan, canRunImport, checkMapping, errorReportCsv, validValues, validateRows,
  type ErrorCode, type PreviewRow,
} from '../../records/importModel';
import { pick } from '../../records/labels';
import { submitAction, type SubmitResult } from '../../records/submitAction';
import type { Caller, RecordsData } from '../../records/types';
import { formatNumber } from '../../lib/format';
import type { Locale } from '../../i18n';
import { ConfirmWrite } from './ConfirmWrite';
import { StatusBadge } from './StatusBadge';
import { downloadCsv } from './download';
import styles from './Records.module.css';

export type ImportWizardProps = { data: RecordsData; entityId: string; caller: Caller };
type Step = 'upload' | 'map' | 'preview' | 'confirm';
const STEPS: Step[] = ['upload', 'map', 'preview', 'confirm'];
type FileError = 'tooBig' | 'excel' | 'unterminatedQuote' | 'empty' | 'tooManyRows' | 'unreadable';

/** Import: upload, map, preview, confirm. Nothing is written until the last step is confirmed, and even then it goes through submitAction. */
export function ImportWizard({ data, entityId, caller }: ImportWizardProps) {
  const t = useTranslations('records.import');
  const te = useTranslations('records.import.errors');
  const tf = useTranslations('records.form');
  const locale = useLocale();
  const plan = buildImportPlan(data, entityId, caller, locale);
  const [step, setStep] = useState<Step>('upload');
  const [headers, setHeaders] = useState<string[]>([]);
  const [body, setBody] = useState<string[][]>([]);
  const [mapping, setMapping] = useState<Array<string | null>>([]);
  const [fileError, setFileError] = useState<FileError | null>(null);
  const [busy, setBusy] = useState(false);
  const [over, setOver] = useState(false);
  const [result, setResult] = useState<SubmitResult | null>(null);
  const hintId = useId();
  const entity = data.entities.find((e) => e.id === entityId);
  const back = entity ? (
    <a className={styles.back} href={`/records/${entityId}/`}><Icon name="back" />{pick(entity.pluralLabels, locale, entityId)}</a>
  ) : null;
  if (!plan) return <p role="alert">{t('noAccess')}</p>; // deny by default: no create tool for this caller
  if (!canRunImport(plan)) {
    return (
      <div className={`${styles.screen} ${styles.narrow}`}>
        {back}
        <header className={styles.pageHead}><h1 className={styles.title}>{t('title', { entity: plan.title })}</h1></header>
        <Alert tone="warning">{plan.blockedRequired.length ? t('blocked', { fields: plan.blockedRequired.join(', ') }) : t('needsApproval')}</Alert>
      </div>
    );
  }

  const labelOf = (id: string) => plan.fields.find((f) => f.id === id)?.label ?? id;
  const issues = checkMapping(mapping, plan);
  const preview = step === 'preview' || step === 'confirm' ? validateRows(body, mapping, plan, data) : null;
  const n = (v: number) => formatNumber(locale as Locale, v, 'latn');

  async function readFile(file: File | undefined) {
    setFileError(null); setResult(null);
    if (!file) return;
    if (/\.xlsx?$/i.test(file.name)) return setFileError('excel'); // TODO(Q-179): parse Excel on the server (DSC-011), not here
    if (file.size > MAX_IMPORT_BYTES) return setFileError('tooBig');
    let text: string;
    try { text = await file.text(); } catch { return setFileError('unreadable'); }
    const parsed = parseCsv(text);
    if (parsed.error) return setFileError(parsed.error);
    const [head, ...rest] = parsed.rows;
    if (!head || rest.length === 0) return setFileError('empty');
    if (rest.length > MAX_IMPORT_ROWS) return setFileError('tooManyRows');
    setHeaders(head.map((h) => h.trim()));
    setBody(rest);
    setMapping(autoMap(head, plan!, data));
    setStep('map');
  }
  const onFile = (e: ChangeEvent<HTMLInputElement>) => void readFile(e.target.files?.[0]);
  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setOver(false);
    void readFile(e.dataTransfer.files?.[0]);
  };

  async function confirm() {
    if (!preview || !plan?.action) return;
    setBusy(true);
    try {
      setResult(await submitAction({ entityId, action: plan.action, values: {}, rows: validValues(preview) }));
    } catch {
      setResult({ status: 'refused' });
    } finally {
      setBusy(false);
    }
  }

  const at = STEPS.indexOf(step);
  const stepper = (
    <ol className={styles.stepper} aria-label={t('steps')}>
      {STEPS.map((s, i) => (
        <li key={s} aria-current={s === step ? 'step' : undefined} data-state={i < at ? 'done' : i === at ? 'current' : 'todo'} className={styles.stepItem}>
          <span className={styles.stepDot} aria-hidden="true">{i < at ? <Icon name="statusDone" /> : i + 1}</span>
          <span>{t(`step.${s}`)}</span>
        </li>
      ))}
    </ol>
  );
  const reset = () => { setStep('upload'); setResult(null); setHeaders([]); setBody([]); setMapping([]); };

  type Row = Record<string, string>;
  const previewColumns: TableColumn<Row>[] = [
    { key: '_line', header: t('preview.line'), rowHeader: true, numeric: true },
    {
      key: '_status', header: t('preview.status'), wrap: true,
      render: (r) => (r._ok === 'true' ? <StatusBadge label={t('preview.valid')} tone="success" /> : <span className={styles.problem}>{r._status}</span>),
    },
    ...plan.fields.filter((f) => mapping.includes(f.id)).map((f): TableColumn<Row> => ({ key: f.id, header: f.label })),
  ];
  const shown: PreviewRow[] = preview ? [...preview.rows.filter((r) => r.errors.length).slice(0, 20), ...preview.rows.filter((r) => !r.errors.length).slice(0, 5)] : [];
  const previewRows: Row[] = shown.map((r) => ({
    ...r.values, _line: String(r.line), _ok: r.errors.length ? 'false' : 'true',
    _status: r.errors.length ? r.errors.map((e) => `${labelOf(e.fieldId)}: ${te(e.code as ErrorCode)}`).join('; ') : t('preview.valid'),
  }));
  const report = () => preview && downloadCsv(`${entityId}-errors.csv`, errorReportCsv(preview, labelOf, (c) => te(c), {
    line: t('report.line'), field: t('report.field'), problem: t('report.problem'), value: t('report.value'),
  }));

  return (
    <div className={`${styles.screen} ${styles.narrow}`}>
      {back}
      <header className={styles.pageHead}>
        <div className={styles.headText}>
          <h1 className={styles.title}>{t('title', { entity: plan.title })}</h1>
          <p className={styles.caption}>{t('stepOf', { n: at + 1, total: STEPS.length })}</p>
        </div>
      </header>
      {stepper}
      {fileError ? <Alert tone="warning" title={t('fileErrorTitle')}>{t(`fileError.${fileError}`)}</Alert> : null}
      {step === 'upload' ? (
        <Card className={styles.stepCard}>
          <p className={styles.body}>{t('upload.intro', { max: n(MAX_IMPORT_ROWS) })}</p>
          <div className={styles.drop} data-over={over ? 'true' : undefined}
            onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)} onDrop={onDrop}>
            <Icon name="sheet" size="md" className={styles.dropIcon} />
            <p className={styles.dropTitle}>{t('upload.drop')}</p>
            <p className={styles.caption}>{t('upload.or')}</p>
            <label className={cx(button.root, button.secondary, button.sm, styles.fileButton)}>
              <Icon name="upload" />
              {t('upload.choose')}
              <VisuallyHidden> ({t('upload.file')})</VisuallyHidden>
              <input type="file" accept=".csv,text/csv" className={styles.fileInput} aria-describedby={hintId} onChange={onFile} />
            </label>
            <p id={hintId} className={styles.caption}>{t('upload.file')}. {t('upload.hint')}</p>
          </div>
        </Card>
      ) : null}
      {step === 'map' ? (
        <Card className={styles.stepCard}>
          <p className={styles.body}>{t('map.intro', { count: body.length })}</p>
          <div className={styles.mapTable} role="group" aria-label={t('step.map')}>
            <div className={styles.mapHead} aria-hidden="true">
              <span>{t('map.fileColumn')}</span>
              <span>{t('map.field')}</span>
            </div>
            {headers.map((h, i) => (
              <div key={i} className={styles.mapRow} data-skipped={mapping[i] ? undefined : 'true'}>
                <span className={styles.mapSource}><bdi>{h}</bdi></span>
                <label className={styles.filter}>
                  <VisuallyHidden>{t('map.column', { header: h })}</VisuallyHidden>
                  <select className={styles.filterSelect} value={mapping[i] ?? ''}
                    onChange={(e) => setMapping(mapping.map((m, j) => (j === i ? e.target.value || null : m)))}>
                    <option value="">{t('map.skip')}</option>
                    {plan.fields.map((f) => <option key={f.id} value={f.id}>{f.required ? `${f.label} *` : f.label}</option>)}
                  </select>
                  <Icon name="chevronDown" className={styles.filterIcon} />
                </label>
              </div>
            ))}
          </div>
          {issues.length ? (
            <Alert tone="warning" title={t('map.fixTitle')}>
              <ul className={styles.issueList}>
                {issues.map((x) => <li key={`${x.code}${x.fieldId}`}>{t(`map.${x.code}`, { field: labelOf(x.fieldId) })}</li>)}
              </ul>
            </Alert>
          ) : null}
          <div className={styles.stepActions}>
            <Button variant="secondary" onClick={reset}>{t('back')}</Button>
            <Button disabled={issues.length > 0} onClick={() => setStep('preview')}>{t('next')}</Button>
          </div>
        </Card>
      ) : null}
      {step === 'preview' && preview ? (
        <Card className={styles.stepCard}>
          <div className={styles.counts}>
            <Badge tone="success" icon={<Icon name="statusDone" />}>{t('preview.validCount', { count: preview.validCount })}</Badge>
            <Badge tone={preview.invalidCount ? 'danger' : 'neutral'} icon={<Icon name={preview.invalidCount ? 'statusStopped' : 'statusOpen'} />}>
              {t('preview.invalidCount', { count: preview.invalidCount })}
            </Badge>
          </div>
          <p className={styles.caption}>{t('preview.note')}</p>
          <Table caption={t('preview.caption')} captionHidden columns={previewColumns} rows={previewRows} rowKey={(_, i) => i}
            empty={<p className={styles.emptyLine}>{t('preview.empty')}</p>} />
          <div className={styles.stepActions}>
            <Button variant="secondary" onClick={() => setStep('map')}>{t('back')}</Button>
            <span className={styles.stepActionsEnd}>
              {preview.invalidCount ? <Button variant="secondary" onClick={report}><Icon name="download" />{t('report.download')}</Button> : null}
              <Button disabled={preview.validCount === 0} onClick={() => setStep('confirm')}>{t('next')}</Button>
            </span>
          </div>
        </Card>
      ) : null}
      {step === 'confirm' && preview ? (
        <>
          {result ? <Alert tone={result.status === 'refused' ? 'warning' : 'info'}>{tf(`result.${result.status}`)}</Alert> : null}
          <ConfirmWrite actionLabel={t('actionLabel')} entityLabel={plan.title} risk={plan.action!.risk}
            changes={[
              { fieldId: '_rows', label: t('confirm.rows'), before: '0', after: String(preview.validCount) },
              ...(preview.invalidCount ? [{ fieldId: '_skipped', label: t('confirm.skipped'), before: '0', after: String(preview.invalidCount) }] : []),
            ]}
            sensitive={plan.action!.effects.ledger || plan.action!.effects.tax || plan.action!.effects.externalSend}
            busy={busy} onConfirm={() => void confirm()} onCancel={() => setStep('preview')} />
        </>
      ) : null}
    </div>
  );
}
