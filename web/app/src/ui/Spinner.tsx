import type { ComponentPropsWithRef } from 'react';
import { cx } from './cx';
import { VisuallyHidden } from './VisuallyHidden';
import styles from './Spinner.module.css';

export type SpinnerProps = Omit<ComponentPropsWithRef<'span'>, 'children'> & {
  /** Accessible name, already translated. Omit only when `decorative` is set. */
  label?: string;
  /** Hide from assistive technology (e.g. inside a button that already says it is busy). */
  decorative?: boolean;
};

export function Spinner({ label, decorative = false, className, ...rest }: SpinnerProps) {
  if (decorative) {
    return <span aria-hidden="true" className={cx(styles.root, className)} {...rest} />;
  }
  return (
    <span role="status" className={cx(styles.wrap, className)} {...rest}>
      <span aria-hidden="true" className={styles.root} />
      {label ? <VisuallyHidden>{label}</VisuallyHidden> : null}
    </span>
  );
}
