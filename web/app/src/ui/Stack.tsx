import type { ComponentPropsWithRef, CSSProperties } from 'react';
import { cx } from './cx';
import styles from './Stack.module.css';

export type StackProps = ComponentPropsWithRef<'div'> & {
  /** Gap in multiples of --space-unit. */
  gap?: 0 | 0.5 | 1 | 1.5 | 2 | 3 | 4 | 6 | 8;
  direction?: 'column' | 'row';
  align?: 'start' | 'center' | 'end' | 'stretch';
  wrap?: boolean;
  as?: 'div' | 'section' | 'ul' | 'ol' | 'form' | 'nav';
};

export function Stack({
  gap = 2,
  direction = 'column',
  align,
  wrap = false,
  as: Tag = 'div',
  className,
  style,
  ...rest
}: StackProps) {
  const vars = { '--stack-gap': gap } as CSSProperties;
  return (
    <Tag
      className={cx(
        styles.root,
        direction === 'row' && styles.row,
        wrap && styles.wrap,
        align && styles[`align_${align}`],
        className,
      )}
      style={{ ...vars, ...style }}
      {...(rest as object)}
    />
  );
}
