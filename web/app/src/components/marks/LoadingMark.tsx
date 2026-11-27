'use client';

import { useTranslations } from 'next-intl';
import { Mark } from '../../ui';
import styles from './Marks.module.css';

/**
 * "Seshna is working" (approved 2026-11-26, docs/brand/09-applications.md): the fill cycles outline, upper half, both halves
 * on a calm loop. Only fill opacity changes; the halves never rotate, scale or move. Under prefers-reduced-motion
 * it shows the static drafted state. The text label is always visible.
 */
export function LoadingMark({ label, size = 20, className }: { label?: string; size?: number; className?: string }) {
  const t = useTranslations('marks');
  return (
    <span role="status" className={className ? `${styles.item} ${className}` : styles.item}>
      <span className={styles.loading} data-loading="true">
        <Mark upper="solid" lower="solid" size={size} />
      </span>
      <span>{label ?? t('loading')}</span>
    </span>
  );
}
