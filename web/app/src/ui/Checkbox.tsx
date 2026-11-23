import { useId, type ComponentPropsWithRef, type ReactNode } from 'react';
import { cx } from './cx';
import styles from './Checkbox.module.css';

export type CheckboxProps = Omit<ComponentPropsWithRef<'input'>, 'type' | 'id' | 'children'> & {
  label: ReactNode;
  hint?: ReactNode;
  error?: ReactNode;
  id?: string;
};

export function Checkbox({ label, hint, error, id: idProp, className, ...rest }: CheckboxProps) {
  const auto = useId();
  const id = idProp ?? auto;
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  return (
    <div className={cx(styles.root, className)}>
      <input
        {...rest}
        id={id}
        type="checkbox"
        className={styles.box}
        aria-describedby={[hintId, errorId].filter(Boolean).join(' ') || undefined}
        aria-invalid={error ? true : undefined}
      />
      <label htmlFor={id} className={styles.label}>
        {label}
      </label>
      {hint ? (
        <div id={hintId} className={styles.note}>
          {hint}
        </div>
      ) : null}
      {error ? (
        <div id={errorId} role="alert" className={cx(styles.note, styles.error)}>
          {error}
        </div>
      ) : null}
    </div>
  );
}
