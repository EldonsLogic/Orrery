import { Badge, type BadgeTone } from '../../ui';

/** A workflow state as text plus tone; the text carries the meaning, colour never stands alone. */
export function StatusBadge({ label, tone = 'neutral' }: { label: string; tone?: BadgeTone }) {
  return <Badge tone={tone}>{label}</Badge>;
}
