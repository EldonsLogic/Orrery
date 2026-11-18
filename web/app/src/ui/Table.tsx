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
              <th key={c.key} scope="col" className={cx(styles.cell, c.numeric && styles.numeric)}>
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && empty ? (
            <tr>
              <td colSpan={columns.length} className={styles.cell}>
                {empty}
              </td>
            </tr>
          ) : (
            rows.map((row, i) => (
              <tr key={rowKey(row, i)}>
                {columns.map((c) =>
                  c.rowHeader ? (
                    <th key={c.key} scope="row" className={cx(styles.cell, styles.rowHeader, c.numeric && styles.numeric)}>
                      {cell(row, c)}
                    </th>
                  ) : (
                    <td key={c.key} className={cx(styles.cell, c.numeric && styles.numeric)}>
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
