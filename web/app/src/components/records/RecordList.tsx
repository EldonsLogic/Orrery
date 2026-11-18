'use client';

import { useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { Button, Select, Stack, Table, TextField, type TableColumn } from '../../ui';
import { buildListModel, defaultQuery, type Cell, type ListQuery, type ListRow } from '../../records/listModel';
import type { Caller, RecordsData } from '../../records/types';
import { StatusBadge } from './StatusBadge';
import styles from './Records.module.css';

export type RecordListProps = { data: RecordsData; entityId: string; caller: Caller; initialQuery?: Partial<ListQuery> };

const cellView = (c: Cell | undefined) => {
  if (!c) return null;
  if (c.kind === 'status') return <StatusBadge label={c.text} tone={c.tone} />;
  if (c.kind === 'money' || c.kind === 'number') return <bdi dir="ltr" className={styles.num}>{c.text}</bdi>;
  if (c.kind === 'date') return <bdi dir="ltr">{c.text}</bdi>;
  if (c.kind === 'link' && c.href) return <a className={styles.link} href={c.href}>{c.text}</a>;
  return c.text;
};

export function RecordList({ data, entityId, caller, initialQuery }: RecordListProps) {
  const t = useTranslations('records.list');
  const locale = useLocale();
  const [query, setQuery] = useState<ListQuery>({ ...defaultQuery, ...initialQuery });
  const model = buildListModel(data, entityId, caller, locale, query);
  if (!model) return <p role="alert">{t('noAccess')}</p>; // deny by default: no list tool for this caller
  const set = (patch: Partial<ListQuery>) => setQuery({ ...model.query, ...patch });
  const sortBy = (field: string) =>
    set({ sort: { field, direction: model.query.sort?.field === field && model.query.sort.direction === 'asc' ? 'desc' : 'asc' }, page: 1 });
  const colLabel = (id: string, label: string) => (id === 'state' ? t('status') : label);

  const columns: TableColumn<ListRow>[] = [
    { key: '_id', header: t('id'), rowHeader: true, render: (r) => (r.href ? <a className={styles.link} href={r.href}>{r.id}</a> : r.id) },
    ...model.columns.map((c): TableColumn<ListRow> => ({
      key: c.id,
      numeric: c.numeric,
      header: c.sortable ? (
        <button type="button" className={styles.sort} onClick={() => sortBy(c.id)} aria-label={t('sortBy', { column: colLabel(c.id, c.label) })}>
          {colLabel(c.id, c.label)}
          {model.query.sort?.field === c.id ? (model.query.sort.direction === 'asc' ? ' (↑)' : ' (↓)') : ''}
        </button>
      ) : colLabel(c.id, c.label),
      render: (r) => cellView(r.cells.find((x) => x.columnId === c.id)),
    })),
  ];

  return (
    <div>
      <div className={styles.head}>
        <h1 className={styles.title}>{model.title}</h1>
        <Stack direction="row" gap={2} align="center" wrap>
          {model.createAction ? <a className={styles.link} href={`/records/${entityId}/new/`}>{t('create')}</a> : null}
          {model.createAction ? <a className={styles.link} href={`/records/${entityId}/import/`}>{t('import')}</a> : null}
          <a className={styles.link} href={`/records/${entityId}/export/`}>{t('export')}</a>
        </Stack>
      </div>
      <div className={styles.bar}>
        <TextField className={styles.grow} type="search" label={t('search')} value={model.query.search} onChange={(e) => set({ search: e.target.value, page: 1 })} />
        {model.columns.filter((c) => c.filter).map((c) => (
          <Select key={c.id} label={t('filterBy', { column: colLabel(c.id, c.label) })} value={model.query.filters[c.id] ?? ''}
            onChange={(e) => set({ filters: { ...model.query.filters, [c.id]: e.target.value }, page: 1 })}>
            <option value="">{t('all')}</option>
            {c.filter!.options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </Select>
        ))}
      </div>
      <Table caption={t('caption', { entity: model.title })} captionHidden columns={columns} rows={model.rows as ListRow[]} rowKey={(r) => r.id} empty={t('empty')} />
      <div className={styles.pager}>
        <span>{t('total', { count: model.total })}</span>
        <Stack direction="row" gap={1} align="center">
          <Button variant="secondary" size="sm" disabled={model.page <= 1} onClick={() => set({ page: model.page - 1 })}>{t('previous')}</Button>
          <span>{t('pageOf', { page: model.page, pageCount: model.pageCount })}</span>
          <Button variant="secondary" size="sm" disabled={model.page >= model.pageCount} onClick={() => set({ page: model.page + 1 })}>{t('next')}</Button>
        </Stack>
      </div>
    </div>
  );
}
