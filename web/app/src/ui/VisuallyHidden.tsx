import type { ComponentPropsWithRef } from 'react';
import { cx } from './cx';
import styles from './VisuallyHidden.module.css';

/** Text for assistive technology only. The text comes from the caller. */
export function VisuallyHidden({ className, ...rest }: ComponentPropsWithRef<'span'>) {
  return <span className={cx(styles.root, className)} {...rest} />;
}
