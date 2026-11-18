import type { ComponentPropsWithRef } from 'react';
import { cx } from './cx';
import { Field, type FieldMessages } from './Field';
import control from './control.module.css';
import styles from './TextField.module.css';

export type TextFieldProps = Omit<ComponentPropsWithRef<'input'>, 'id' | 'children'> &
  FieldMessages & {
    /**
     * Numeric content (amounts, quantities, codes): digits stay left-to-right and readable
     * inside a right-to-left page; sets inputMode to "decimal" unless given.
     */
    numeric?: boolean;
  };

export function TextField({
  label,
  hint,
  error,
  requiredMark,
  id,
  numeric = false,
  required,
  dir,
  inputMode,
  className,
  ...rest
}: TextFieldProps) {
  return (
    <Field label={label} hint={hint} error={error} requiredMark={requiredMark} id={id} className={className}>
      {(wiring) => (
        <input
          {...rest}
          {...wiring}
          required={required}
          dir={dir ?? (numeric ? 'ltr' : 'auto')}
          inputMode={inputMode ?? (numeric ? 'decimal' : undefined)}
          className={cx(control.control, numeric && styles.numeric)}
        />
      )}
    </Field>
  );
}
