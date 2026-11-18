'use client';

import { useState, type ChangeEvent } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { Alert, Badge, Button, Select, Stack, Table, TextField, type TableColumn } from '../../ui';
import { parseCsv } from '../../records/csv';
import {
  MAX_IMPORT_BYTES, MAX_IMPORT_ROWS, autoMap, buildImportPlan, canRunImport, checkMapping, errorReportCsv, validValues, validateRows,
  type ErrorCode, type PreviewRow,
} from '../../records/importModel';
import { submitAction, type SubmitResult } from '../../records/submitAction';
import type { Caller, RecordsData } from '../../records/types';
import { ConfirmWrite } from './ConfirmWrite';
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
  const [result, setResult] = useState<SubmitResult | null>(null);
  if (!plan) return <p role="alert">{t('noAccess')}</p>; // deny by default: no create tool for this caller
  if (!canRunImport(plan)) {
    return (
      <div>
        <div className={styles.head}><h1 className={styles.title}>{t('title', { entity: plan.title })}</h1></div>
        <Alert tone="warning">{plan.blockedRequired.length ? t('blocked', { fields: plan.blockedRequired.join(', ') }) : t('needsApproval')}</Alert>
      </div>
    );
  }

  const labelOf = (id: string) => plan.fields.find((f) => f.id === id)?.label ?? id;
  const issues = checkMapping(mapping, plan);
  const preview = step === 'preview' || step === 'confirm' ? validateRows(body, mapping, plan, data) : null;

  async function onFile(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
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

  const stepper = (
    <ol className={styles.steps} aria-label={t('steps')}>
      {STEPS.map((s) => <li key={s} aria-current={s === step ? 'step' : undefined}>{t(`step.${s}`)}</li>)}
    </ol>
  );
  const reset = () => { setStep('upload'); setResult(null); setHeaders([]); setBody([]); setMapping([]); };

  type Row = Record<string, string>;
  const previewColumns: TableColumn<Row>[] = [
    { key: '_line', header: t('preview.line'), rowHeader: true },
    { key: '_status', header: t('preview.status') },
    ...plan.fields.filter((f) => mapping.includes(f.id)).map((f): TableColumn<Row> => ({ key: f.id, header: f.label })),
  ];
  const shown: PreviewRow[] = preview ? [...preview.rows.filter((r) => r.errors.length).slice(0, 20), ...preview.rows.filter((r) => !r.errors.length).slice(0, 5)] : [];
  const previewRows: Row[] = shown.map((r) => ({
    ...r.values, _line: String(r.line),
    _status: r.errors.length ? r.errors.map((e) => `${labelOf(e.fieldId)}: ${te(e.code as ErrorCode)}`).join('; ') : t('preview.valid'),
  }));
  const report = () => preview && downloadCsv(`${entityId}-errors.csv`, errorReportCsv(preview, labelOf, (c) => te(c), {
    line: t('report.line'), field: t('report.field'), problem: t('report.problem'), value: t('report.value'),
  }));

  return (
    <div>
      <div className={styles.head}><h1 className={styles.title}>{t('title', { entity: plan.title })}</h1></div>
      {stepper}
      {fileError ? <Alert tone="warning">{t(`fileError.${fileError}`)}</Alert> : null}
      {step === 'upload' ? (
        <Stack gap={2}>
          <p>{t('upload.intro', { max: MAX_IMPORT_ROWS })}</p>
          <TextField type="file" accept=".csv,text/csv" label={t('upload.file')} hint={t('upload.hint')} onChange={(e) => void onFile(e)} />
          <a className={styles.link} href={`/records/${entityId}/`}>{t('back')}</a>
        </Stack>
      ) : null}
      {step === 'map' ? (
        <Stack gap={2}>
          <p>{t('map.intro', { count: body.length })}</p>
          {headers.map((h, i) => (
            <Select key={i} label={t('map.column', { header: h })} value={mapping[i] ?? ''}
              onChange={(e) => setMapping(mapping.map((m, j) => (j === i ? e.target.value || null : m)))}>
              <option value="">{t('map.skip')}</option>
              {plan.fields.map((f) => <option key={f.id} value={f.id}>{f.required ? `${f.label} *` : f.label}</option>)}
            </Select>
          ))}
          {issues.map((x) => <Alert key={`${x.code}${x.fieldId}`} tone="warning">{t(`map.${x.code}`, { field: labelOf(x.fieldId) })}</Alert>)}
          <Stack direction="row" gap={1} wrap>
            <Button disabled={issues.length > 0} onClick={() => setStep('preview')}>{t('next')}</Button>
            <Button variant="secondary" onClick={reset}>{t('back')}</Button>
          </Stack>
        </Stack>
      ) : null}
      {step === 'preview' && preview ? (
        <Stack gap={2}>
          <p>
            <Badge tone="success">{t('preview.validCount', { count: preview.validCount })}</Badge>{' '}
            <Badge tone={preview.invalidCount ? 'danger' : 'neutral'}>{t('preview.invalidCount', { count: preview.invalidCount })}</Badge>
          </p>
          <p>{t('preview.note')}</p>
          <Table caption={t('preview.caption')} captionHidden columns={previewColumns} rows={previewRows} rowKey={(_, i) => i} empty={t('preview.empty')} />
          <Stack direction="row" gap={1} wrap>
            <Button disabled={preview.validCount === 0} onClick={() => setStep('confirm')}>{t('next')}</Button>
            {preview.invalidCount ? <Button variant="secondary" onClick={report}>{t('report.download')}</Button> : null}
            <Button variant="secondary" onClick={() => setStep('map')}>{t('back')}</Button>
          </Stack>
        </Stack>
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
