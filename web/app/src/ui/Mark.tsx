import { useId } from 'react';
import { cx } from './cx';
import styles from './Mark.module.css';

/**
 * The Seshna mark (Nuqta S) as two halves, each solid or outline (BRD-014, docs/brand/09-applications.md).
 * Geometry is copied from docs/brand/logo/mark-primary.svg (master) and mark-small.svg (small-size cut);
 * each file's single path holds the upper half then the lower half. The outline is drawn inside the half's
 * own silhouette (stroke clipped to the shape), so outline and solid halves have the same footprint.
 * Misuse rules: never rotated, mirrored, stretched, split or transformed; colour comes from tokens only.
 */
export type MarkFill = 'solid' | 'outline';
export type MarkTone = 'primary' | 'accent';

const CUTS = {
  master: {
    upper: 'M40.82 103.18 L128 16 L177.64 65.64 L90.45 152.82 A35.1 35.1 0 0 1 40.82 103.18 Z',
    lower: 'M215.18 152.82 L128 240 L78.36 190.36 L165.55 103.18 A35.1 35.1 0 0 1 215.18 152.82 Z',
    stroke: 16,
  },
  small: {
    upper: 'M32.32 103.68 L128 8 L176.64 56.64 L80.95 152.32 A34.39 34.39 0 0 1 32.32 103.68 Z',
    lower: 'M223.68 152.32 L128 248 L79.36 199.36 L175.05 103.68 A34.39 34.39 0 0 1 223.68 152.32 Z',
    stroke: 22,
  },
} as const;

/** Below this size (px) the small-size cut is used (docs/brand/02-logo.md). */
export const SMALL_CUT_BELOW = 24;

export type MarkProps = {
  upper?: MarkFill;
  lower?: MarkFill;
  /** Rendered size in px (square). */
  size?: number;
  /** Cobalt (primary) by default; Coral (accent) at most once per view, always beside a text label. */
  tone?: MarkTone;
  className?: string;
  /** Accessible name. Omit when visible text next to the mark already says what it means (the usual case). */
  title?: string;
};

export function Mark({ upper = 'solid', lower = 'solid', size = 24, tone = 'primary', className, title }: MarkProps) {
  const cutName = size < SMALL_CUT_BELOW ? 'small' : 'master';
  const cut = CUTS[cutName];
  const uid = useId().replace(/[^A-Za-z0-9_-]/g, '');
  const a11y = title ? { role: 'img', 'aria-label': title } : { 'aria-hidden': true };
  const half = (h: 'upper' | 'lower', fill: MarkFill) => {
    const clip = `mk-${uid}-${h}`;
    return (
      <g key={h}>
        <clipPath id={clip}>
          <path d={cut[h]} />
        </clipPath>
        <path
          data-half={h}
          data-fill={fill}
          d={cut[h]}
          fill={fill === 'solid' ? 'currentColor' : 'none'}
          stroke="currentColor"
          strokeWidth={cut.stroke * 2}
          clipPath={`url(#${clip})`}
        />
      </g>
    );
  };
  return (
    <svg
      viewBox="0 0 256 256"
      width={size}
      height={size}
      focusable="false"
      data-cut={cutName}
      className={cx(styles.root, tone === 'accent' && styles.accent, className)}
      {...a11y}
    >
      {half('upper', upper)}
      {half('lower', lower)}
    </svg>
  );
}
