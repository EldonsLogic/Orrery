import type { Key, ReactNode } from 'react';
import { cx } from './cx';
import { VisuallyHidden } from './VisuallyHidden';
import styles from './Table.module.css';

export type TableColumn<Row> = {
  key: string;
  /** Column header, already translated. */
  header: ReactNode;
  /** Right-aligned in LTR, left-aligned in RTL (logical end), with tabular digits. */
  numeric?: boolean;
  /** Render cells of this column as row headers (`<th scope="row">`). Use for the identifying column. */
  rowHeader?: boolean;
  /** The column the rows are sorted by, for assistive technology (aria-sort). */
  sort?: 'ascending' | 'descending';
  /** Let long text wrap instead of widening the table. */
  wrap?: boolean;
  /** Extra class on the column's header and cells (for example to hide a column on narrow screens). */
  className?: string;
  render?: (row: Row) => ReactNode;
};

export type TableProps<Row> = {
  /** Required accessible caption, already translated. */
  caption: ReactNode;
  /** Keep the caption for assistive technology only. */
  captionHidden?: boolean;
  columns: ReadonlyArray<TableColumn<Row>>;
  rows: ReadonlyArray<Row>;
  rowKey: (row: Row, index: number) => Key;
  /** Shown in place of rows when `rows` is empty, already translated. */
  empty?: ReactNode;
  className?: string;
};

export function Table<Row extends Record<string, unknown>>({
  caption,
  captionHidden = false,
  columns,
  rows,
  rowKey,
  empty,
  className,
}: TableProps<Row>) {
  const cell = (row: Row, c: TableColumn<Row>): ReactNode =>
    c.render ? c.render(row) : (row[c.key] as ReactNode);
  return (
    <div className={cx(styles.wrap, className)}>
      <table className={styles.table}>
        {captionHidden ? (
          <caption>
            <VisuallyHidden>{caption}</VisuallyHidden>
          </caption>
        ) : (
          <caption className={styles.caption}>{caption}</caption>
        )}
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key} scope="col" aria-sort={c.sort} className={cx(styles.cell, c.numeric && styles.numeric, c.className)}>
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && empty ? (
            <tr>
              <td colSpan={columns.length} className={cx(styles.cell, styles.emptyCell)}>
                {empty}
              </td>
            </tr>
          ) : (
            rows.map((row, i) => (
              <tr key={rowKey(row, i)}>
                {columns.map((c) =>
                  c.rowHeader ? (
                    <th key={c.key} scope="row" className={cx(styles.cell, styles.rowHeader, c.numeric && styles.numeric, c.wrap && styles.wrapText, c.className)}>
                      {cell(row, c)}
                    </th>
                  ) : (
                    <td key={c.key} className={cx(styles.cell, c.numeric && styles.numeric, c.wrap && styles.wrapText, c.className)}>
                      {cell(row, c)}
                    </td>
                  ),
                )}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
