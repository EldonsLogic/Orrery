import type { ComponentPropsWithRef, ReactNode } from 'react';
import { cx } from './cx';
import styles from './Badge.module.css';

export type BadgeTone = 'success' | 'warning' | 'danger' | 'neutral';

export type BadgeProps = ComponentPropsWithRef<'span'> & {
  tone?: BadgeTone;
  /** Optional decorative icon. The text child always carries the meaning, so colour is never alone. */
  icon?: ReactNode;
};

export function Badge({ tone = 'neutral', icon, className, children, ...rest }: BadgeProps) {
  return (
    <span className={cx(styles.root, styles[tone], className)} {...rest}>
      {icon ? (
        <span aria-hidden="true" className={styles.icon}>
          {icon}
        </span>
      ) : null}
      {children}
    </span>
  );
}
