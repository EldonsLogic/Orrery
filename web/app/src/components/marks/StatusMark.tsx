'use client';

import { useTranslations } from 'next-intl';
import { Mark, type MarkFill } from '../../ui';
import styles from './Marks.module.css';

export const STATUS_MARKS = ['not_started', 'drafted', 'approved'] as const;
export type StatusMarkKind = (typeof STATUS_MARKS)[number];

const HALVES: Record<StatusMarkKind, [MarkFill, MarkFill]> = {
  not_started: ['outline', 'outline'],
  drafted: ['solid', 'outline'],
  approved: ['solid', 'solid'],
};

/** Not started, drafted by the AI, approved by a person (brand kit "Status"). The mark always sits beside its word. */
export function StatusMark({ status, size = 20, className }: { status: StatusMarkKind; size?: number; className?: string }) {
  const t = useTranslations('marks.status');
  const [upper, lower] = HALVES[status];
  return (
    <span className={className ? `${styles.item} ${className}` : styles.item} data-status={status}>
      <Mark upper={upper} lower={lower} size={size} />
      <span>{t(status)}</span>
    </span>
  );
}
