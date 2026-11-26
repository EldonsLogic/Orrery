import { Badge, Icon, type BadgeTone, type IconName } from '../../ui';
import styles from './Records.module.css';

// One glyph per tone (placeholders until the Seshna icon set, see ui/Icon.tsx): the word carries the meaning, the icon backs it up.
const GLYPH: Record<BadgeTone, IconName> = { neutral: 'statusOpen', warning: 'statusWaiting', success: 'statusDone', danger: 'statusStopped' };

/** A workflow state as a word, an icon and a tone; colour never stands alone. */
export function StatusBadge({ label, tone = 'neutral' }: { label: string; tone?: BadgeTone }) {
  return (
    <Badge tone={tone} icon={<Icon name={GLYPH[tone]} />} data-tone={tone} className={styles.status}>
      {label}
    </Badge>
  );
}
