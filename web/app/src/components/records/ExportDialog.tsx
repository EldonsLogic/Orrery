'use client';

import { useLocale, useTranslations } from 'next-intl';
import { Alert, Button, Card, Icon, Table, type TableColumn } from '../../ui';
import { buildExportModel } from '../../records/exportModel';
import { pick } from '../../records/labels';
import type { Caller, RecordsData } from '../../records/types';
import { formatNumber } from '../../lib/format';
import type { Locale } from '../../i18n';
import { downloadCsv } from './download';
import styles from './Records.module.css';

export type ExportDialogProps = { data: RecordsData; entityId: string; caller: Caller };

/** Export: shows what will be in the file (only fields the caller may see), then offers the CSV. Excel waits for the server (Q-179). */
export function ExportDialog({ data, entityId, caller }: ExportDialogProps) {
  const t = useTranslations('records.export');
  const locale = useLocale();
  const model = buildExportModel(data, entityId, caller, locale, t('id'));
  if (!model) return <p role="alert">{t('noAccess')}</p>; // deny by default
  const entity = data.entities.find((e) => e.id === entityId);
  const n = (v: number) => formatNumber(locale as Locale, v, 'latn');
  type Row = Record<string, string>;
  const columns: TableColumn<Row>[] = model.headers.map((h, i) => ({ key: String(i), header: h, rowHeader: i === 0 }));
  const preview: Row[] = model.rows.slice(0, 5).map((r) => Object.fromEntries(r.map((c, i) => [String(i), c])));
  return (
    <div className={`${styles.screen} ${styles.narrow}`}>
      {entity ? <a className={styles.back} href={`/records/${entityId}/`}><Icon name="back" />{pick(entity.pluralLabels, locale, entityId)}</a> : null}
      <header className={styles.pageHead}>
        <div className={styles.headText}>
          <h1 className={styles.title}>{t('title', { entity: model.title })}</h1>
          <p className={styles.caption}>{t('intro', { count: model.rows.length, columns: model.headers.length })}</p>
        </div>
      </header>
      <Card className={styles.stepCard}>
        <dl className={styles.facts}>
          <div><dt>{t('records')}</dt><dd><bdi dir="ltr" className={styles.num}>{n(model.rows.length)}</bdi></dd></div>
          <div><dt>{t('columns')}</dt><dd><bdi dir="ltr" className={styles.num}>{n(model.headers.length)}</bdi></dd></div>
          <div><dt>{t('format')}</dt><dd>{t('csv')}</dd></div>
        </dl>
        <h2 className={styles.sectionTitle}>{t('preview')}</h2>
        <Table caption={t('previewCaption')} captionHidden columns={columns} rows={preview} rowKey={(_, i) => i}
          empty={<p className={styles.emptyLine}>{t('empty')}</p>} />
        <Alert tone="info">{t('excelLater')}</Alert>
        <div className={styles.stepActions}>
          <a className={styles.textLink} href={`/records/${entityId}/`}>{t('back')}</a>
          <Button onClick={() => downloadCsv(model.fileName, model.csv)}><Icon name="download" />{t('downloadCsv')}</Button>
        </div>
      </Card>
    </div>
  );
}
