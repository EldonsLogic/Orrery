import type { ComponentPropsWithRef, ReactNode } from 'react';
import { cx } from './cx';
import styles from './Alert.module.css';

export type AlertTone = 'info' | 'success' | 'warning' | 'danger';

export type AlertProps = Omit<ComponentPropsWithRef<'div'>, 'title'> & {
  tone?: AlertTone;
  /** Short heading, already translated. It also keeps the tone readable without colour. */
  title?: ReactNode;
  /** Optional decorative icon. */
  icon?: ReactNode;
};

/** Warning and danger interrupt (role "alert"); info and success are polite (role "status"). */
export function Alert({ tone = 'info', title, icon, className, children, role, ...rest }: AlertProps) {
  const defaultRole = tone === 'danger' || tone === 'warning' ? 'alert' : 'status';
  return (
    <div role={role ?? defaultRole} className={cx(styles.root, styles[tone], className)} {...rest}>
      {icon ? (
        <span aria-hidden="true" className={styles.icon}>
          {icon}
        </span>
      ) : null}
      <div className={styles.body}>
        {title ? <div className={styles.title}>{title}</div> : null}
        {children ? <div>{children}</div> : null}
      </div>
    </div>
  );
}
