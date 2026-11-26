'use client';

import { useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { Button, Icon, Table, VisuallyHidden, type TableColumn } from '../../ui';
import { cx } from '../../ui/cx';
import button from '../../ui/Button.module.css';
import { buildListModel, defaultQuery, type ListModel, type ListQuery, type ListRow } from '../../records/listModel';
import type { Caller, RecordsData } from '../../records/types';
import { CellView, keep } from './Cells';
import styles from './Records.module.css';

export type RecordListProps = { data: RecordsData; entityId: string; caller: Caller; initialQuery?: Partial<ListQuery> };

/** The list screen shows 25 rows a page (the model's own default stays 5 for its tests and callers). */
export const LIST_PAGE_SIZE = 25;

const linkButton = (variant: 'primary' | 'secondary') => cx(button.root, button[variant], button.sm);

/** Phones: each row becomes a card that links to its record (id, status, the first text column, a date and the last amount). */
function Cards({ model }: { model: ListModel }) {
  const by = (kind: string) => model.columns.find((c) => c.kind === kind);
  const status = by('status');
  const subtitle = model.columns.find((c) => c.kind === 'text' || c.kind === 'link');
  const date = by('date');
  const amount = [...model.columns].reverse().find((c) => c.kind === 'money');
  const cell = (row: ListRow, id?: string) => (id ? row.cells.find((c) => c.columnId === id) : undefined);
  return (
    <ul className={styles.cards} data-layout="cards">
      {model.rows.map((row) => {
        const body = (
          <>
            <span className={styles.cardTop}>
              <span className={styles.cardId}>{keep(row.id)}</span>
              {status ? <CellView cell={cell(row, status.id)} /> : null}
            </span>
            <span className={styles.cardBottom}>
              <span className={styles.cardMeta}>
                {subtitle ? <span className={styles.cardTitle}><CellView cell={cell(row, subtitle.id)} plain /></span> : null}
                {date ? <span className={styles.cardDate}><CellView cell={cell(row, date.id)} /></span> : null}
              </span>
              {amount ? <span className={styles.cardAmount}><CellView cell={cell(row, amount.id)} /></span> : null}
            </span>
          </>
        );
        return (
          <li key={row.id}>
            {row.href ? <a className={styles.card} href={row.href}>{body}</a> : <div className={styles.card}>{body}</div>}
          </li>
        );
      })}
    </ul>
  );
}

/** Shown while the list loads: the shape of the screen, static (no shimmer), announced as busy. */
export function RecordListSkeleton() {
  const t = useTranslations('records.list');
  return (
    <div className={styles.screen} aria-busy="true">
      <VisuallyHidden role="status">{t('loading')}</VisuallyHidden>
      <div className={styles.pageHead} aria-hidden="true">
        <span className={cx(styles.bone, styles.boneTitle)} />
      </div>
      <div className={styles.skeleton} aria-hidden="true">
        {Array.from({ length: 6 }, (_, i) => (
          <span key={i} className={styles.skeletonRow}>
            <span className={cx(styles.bone, styles.boneShort)} />
            <span className={styles.bone} />
            <span className={cx(styles.bone, styles.boneShort)} />
          </span>
        ))}
      </div>
    </div>
  );
}

export function RecordList({ data, entityId, caller, initialQuery }: RecordListProps) {
  const t = useTranslations('records.list');
  const locale = useLocale();
  const [query, setQuery] = useState<ListQuery>({ ...defaultQuery, pageSize: LIST_PAGE_SIZE, ...initialQuery });
  const model = buildListModel(data, entityId, caller, locale, query);
  if (!model) return <p role="alert">{t('noAccess')}</p>; // deny by default: no list tool for this caller
  const set = (patch: Partial<ListQuery>) => setQuery({ ...model.query, ...patch });
  const sortBy = (field: string) =>
    set({ sort: { field, direction: model.query.sort?.field === field && model.query.sort.direction === 'asc' ? 'desc' : 'asc' }, page: 1 });
  const colLabel = (id: string, label: string) => (id === 'state' ? t('status') : label);
  const narrowed = model.query.search.trim() !== '' || Object.values(model.query.filters).some(Boolean);
  const clear = () => set({ search: '', filters: {}, page: 1 });
  const icon = (dir?: 'asc' | 'desc') => <Icon name={dir === 'asc' ? 'arrowUp' : dir === 'desc' ? 'arrowDown' : 'chevronsUpDown'} className={styles.sortIcon} />;
  const sortOf = (id: string) => (model.query.sort?.field === id ? model.query.sort.direction : undefined);

  // Intermediate totals (a document's read-only amounts before the last one, such as subtotal and tax) give way first on narrow screens.
  const entity = data.entities.find((e) => e.id === entityId);
  const amounts = entity?.kind === 'document' ? entity.fields.filter((f) => f.type === 'money' && (f.readOnly || f.computed !== undefined)).map((f) => f.id) : [];
  const secondary = new Set(amounts.slice(0, -1));

  const columns: TableColumn<ListRow>[] = [
    { key: '_id', header: t('id'), rowHeader: true, render: (r) => (r.href ? <a className={styles.rowLink} href={r.href}>{keep(r.id)}</a> : keep(r.id)) },
    ...model.columns.map((c): TableColumn<ListRow> => {
      const dir = sortOf(c.id);
      return {
        key: c.id,
        numeric: c.numeric,
        className: secondary.has(c.id) ? styles.secondaryColumn : undefined,
        sort: dir === 'asc' ? 'ascending' : dir === 'desc' ? 'descending' : undefined,
        header: c.sortable ? (
          <button type="button" className={styles.sort} data-active={dir ? 'true' : undefined} onClick={() => sortBy(c.id)}
            aria-label={t('sortBy', { column: colLabel(c.id, c.label) })}>
            {/* In figure columns the icon goes first, so the label ends on the same line as the figures. */}
            {c.numeric ? icon(dir) : null}
            {colLabel(c.id, c.label)}
            {c.numeric ? null : icon(dir)}
          </button>
        ) : colLabel(c.id, c.label),
        render: (r) => <CellView cell={r.cells.find((x) => x.columnId === c.id)} />,
      };
    }),
  ];

  const first = model.total === 0 ? 0 : (model.page - 1) * model.query.pageSize + 1;
  const last = Math.min(model.total, model.page * model.query.pageSize);
  const empty = (
    <div className={styles.empty}>
      <Icon name="empty" size="md" className={styles.emptyIcon} />
      <p className={styles.emptyTitle}>{narrowed ? t('emptyTitle') : t('noneTitle')}</p>
      <p className={styles.caption}>{narrowed ? t('emptyBody') : t('noneBody')}</p>
      {narrowed ? <Button variant="secondary" size="sm" onClick={clear}>{t('clearFilters')}</Button> : null}
    </div>
  );

  return (
    <div className={styles.screen}>
      <header className={styles.pageHead}>
        <div className={styles.headText}>
          <h1 className={styles.title}>{model.title}</h1>
          <p className={styles.caption}>{t('total', { count: model.total })}</p>
        </div>
        <div className={styles.headActions}>
          {model.createAction ? (
            <a className={linkButton('secondary')} href={`/records/${entityId}/import/`}><Icon name="upload" />{t('import')}</a>
          ) : null}
          <a className={linkButton('secondary')} href={`/records/${entityId}/export/`}><Icon name="download" />{t('export')}</a>
          {model.createAction ? (
            <a className={linkButton('primary')} href={`/records/${entityId}/new/`}><Icon name="plus" />{t('create')}</a>
          ) : null}
        </div>
      </header>

      <div className={styles.toolbar} role="search" aria-label={t('toolbar')}>
        <label className={styles.search}>
          <VisuallyHidden>{t('search')}</VisuallyHidden>
          <Icon name="search" className={styles.searchIcon} />
          <input type="search" className={styles.searchInput} value={model.query.search} placeholder={t('searchPlaceholder')}
            onChange={(e) => set({ search: e.target.value, page: 1 })} />
        </label>
        {model.columns.filter((c) => c.filter).map((c) => (
          <label key={c.id} className={styles.filter} data-active={model.query.filters[c.id] ? 'true' : undefined}>
            <VisuallyHidden>{t('filterBy', { column: colLabel(c.id, c.label) })}</VisuallyHidden>
            <select className={styles.filterSelect} value={model.query.filters[c.id] ?? ''}
              onChange={(e) => set({ filters: { ...model.query.filters, [c.id]: e.target.value }, page: 1 })}>
              <option value="">{t('filterAll', { column: colLabel(c.id, c.label) })}</option>
              {c.filter!.options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
            <Icon name="chevronDown" className={styles.filterIcon} />
          </label>
        ))}
        {narrowed ? (
          <Button variant="ghost" size="sm" onClick={clear}><Icon name="close" />{t('clearFilters')}</Button>
        ) : null}
      </div>

      {model.rows.length === 0 ? (
        empty
      ) : (
        <>
          <Table className={styles.tableView} caption={t('caption', { entity: model.title })} captionHidden columns={columns}
            rows={model.rows as ListRow[]} rowKey={(r) => r.id} />
          <Cards model={model} />
        </>
      )}

      <footer className={styles.pager}>
        <span className={styles.range}>{t.rich('range', { from: first, to: last, count: model.total, n: (c) => <bdi dir="ltr" className={styles.num}>{c}</bdi> })}</span>
        {model.pageCount > 1 ? (
          <nav className={styles.pages} aria-label={t('pages')}>
            <span>{t('pageOf', { page: model.page, pageCount: model.pageCount })}</span>
            <Button variant="secondary" size="sm" disabled={model.page <= 1} onClick={() => set({ page: model.page - 1 })}>
              <Icon name="pageBack" />{t('previous')}
            </Button>
            <Button variant="secondary" size="sm" disabled={model.page >= model.pageCount} onClick={() => set({ page: model.page + 1 })}>
              {t('next')}<Icon name="pageForward" />
            </Button>
          </nav>
        ) : null}
      </footer>
    </div>
  );
}
