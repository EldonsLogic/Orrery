import type { ComponentPropsWithRef } from 'react';
import { cx } from './cx';
import styles from './Card.module.css';

export type CardProps = ComponentPropsWithRef<'div'> & {
  /** Element to render. Use "section" or "article" with an aria-label or heading when it is a landmark. */
  as?: 'div' | 'section' | 'article' | 'aside';
};

export function Card({ as: Tag = 'div', className, ...rest }: CardProps) {
  return <Tag className={cx(styles.root, className)} {...rest} />;
}
