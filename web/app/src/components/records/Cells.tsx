import type { Cell } from '../../records/listModel';
import type { Money } from '../../records/types';
import { groupDigits } from '../../records/detailModel';
import { StatusBadge } from './StatusBadge';
import styles from './Records.module.css';

/** Document numbers never break at their hyphen (non-breaking hyphen), in either direction. */
export const keep = (ref: string) => ref.replace(/-/g, '‑');

/** An amount: grouped figure in tabular digits, then the currency code as a muted label; one left-to-right isolate, never mirrored. */
export function MoneyText({ money, className }: { money: Money; className?: string }) {
  return (
    <bdi dir="ltr" className={className ? `${styles.money} ${className}` : styles.money}>
      <span className={styles.figure}>{groupDigits(money.value)}</span> <span className={styles.currency}>{money.currency}</span>
    </bdi>
  );
}

/** A cell's content. `plain` drops links (inside a card that is itself a link). */
export function CellView({ cell, plain = false }: { cell: Cell | undefined; plain?: boolean }) {
  if (!cell) return null;
  if (cell.kind === 'status') return cell.text ? <StatusBadge label={cell.text} tone={cell.tone} /> : null;
  if (cell.kind === 'money' && cell.money) return <MoneyText money={cell.money} />;
  if (cell.kind === 'number') return <bdi dir="ltr" className={styles.num}>{groupDigits(cell.text)}</bdi>;
  if (cell.kind === 'date') return <span className={styles.date}><bdi dir="ltr">{cell.text}</bdi></span>;
  if (cell.kind === 'link' && cell.href && !plain) return <a className={styles.cellLink} href={cell.href}>{cell.text}</a>;
  return <>{cell.text}</>;
}
