import type { ComponentPropsWithRef } from 'react';
import { Field, type FieldMessages } from './Field';
import { cx } from './cx';
import control from './control.module.css';
import styles from './Select.module.css';

export type SelectProps = Omit<ComponentPropsWithRef<'select'>, 'id'> & FieldMessages;

/** Native select with label, hint and error. Pass `<option>` children. */
export function Select({ label, hint, error, requiredMark, id, className, children, ...rest }: SelectProps) {
  return (
    <Field label={label} hint={hint} error={error} requiredMark={requiredMark} id={id} className={className}>
      {(wiring) => (
        <select {...rest} {...wiring} className={cx(control.control, styles.select)}>
          {children}
        </select>
      )}
    </Field>
  );
}
