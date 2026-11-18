'use client';

import { useLocale, useTranslations } from 'next-intl';
import { Alert, Button, Stack, Table, type TableColumn } from '../../ui';
import { buildExportModel } from '../../records/exportModel';
import type { Caller, RecordsData } from '../../records/types';
import { downloadCsv } from './download';
import styles from './Records.module.css';

export type ExportDialogProps = { data: RecordsData; entityId: string; caller: Caller };

/** Export: shows what will be in the file (only fields the caller may see), then offers the CSV. Excel waits for the server (Q-179). */
export function ExportDialog({ data, entityId, caller }: ExportDialogProps) {
  const t = useTranslations('records.export');
  const locale = useLocale();
  const model = buildExportModel(data, entityId, caller, locale, t('id'));
  if (!model) return <p role="alert">{t('noAccess')}</p>; // deny by default
  type Row = Record<string, string>;
  const columns: TableColumn<Row>[] = model.headers.map((h, i) => ({ key: String(i), header: h, rowHeader: i === 0 }));
  const preview: Row[] = model.rows.slice(0, 5).map((r) => Object.fromEntries(r.map((c, i) => [String(i), c])));
  return (
    <div>
      <div className={styles.head}><h1 className={styles.title}>{t('title', { entity: model.title })}</h1></div>
      <Stack gap={2}>
        <p>{t('intro', { count: model.rows.length, columns: model.headers.length })}</p>
        <Table caption={t('previewCaption')} captionHidden columns={columns} rows={preview} rowKey={(_, i) => i} empty={t('empty')} />
        <Alert tone="info">{t('excelLater')}</Alert>
        <Stack direction="row" gap={1} wrap>
          <Button onClick={() => downloadCsv(model.fileName, model.csv)}>{t('downloadCsv')}</Button>
          <a className={styles.link} href={`/records/${entityId}/`}>{t('back')}</a>
        </Stack>
      </Stack>
    </div>
  );
}
