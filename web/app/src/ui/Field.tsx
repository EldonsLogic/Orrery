import { useId, type ReactNode } from 'react';
import { cx } from './cx';
import styles from './Field.module.css';
import hidden from './VisuallyHidden.module.css';

export type FieldMessages = {
  /** Visible label, already translated. */
  label: ReactNode;
  hint?: ReactNode;
  /** Error text, already translated. Presence marks the control invalid. */
  error?: ReactNode;
  /** Visible marker for required fields (for example the translated word or an asterisk). */
  requiredMark?: ReactNode;
  id?: string;
  /** Keep the label for assistive technology only, when a visible heading beside the control already names it. */
  labelHidden?: boolean;
};

type Wiring = {
  id: string;
  'aria-describedby': string | undefined;
  'aria-invalid': true | undefined;
};

/** Shared label, hint and error wiring for form controls. Internal to the library. */
export function Field({
  label,
  hint,
  error,
  requiredMark,
  id: idProp,
  labelHidden = false,
  className,
  children,
}: FieldMessages & { className?: string; children: (wiring: Wiring) => ReactNode }) {
  const auto = useId();
  const id = idProp ?? auto;
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(' ') || undefined;
  return (
    <div className={cx(styles.root, className)}>
      <label htmlFor={id} className={cx(styles.label, labelHidden && hidden.root)} data-label-hidden={labelHidden ? 'true' : undefined}>
        {label}
        {requiredMark ? <span className={styles.mark}> {requiredMark}</span> : null}
      </label>
      {hint ? (
        <div id={hintId} className={styles.hint}>
          {hint}
        </div>
      ) : null}
      {children({ id, 'aria-describedby': describedBy, 'aria-invalid': error ? true : undefined })}
      {error ? (
        <div id={errorId} role="alert" className={styles.error}>
          {error}
        </div>
      ) : null}
    </div>
  );
}
