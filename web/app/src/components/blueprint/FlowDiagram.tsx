import type { FlowModel } from '../../blueprint/types';
import styles from './Blueprint.module.css';

const W = 132;
const H = 52;
const GAP_X = 64;
const GAP_Y = 28;
const PAD = 20;
const BACK = 44;

// Two short lines at most, so long labels (Arabic too) stay inside the box.
const wrap = (text: string, max = 16): string[] => {
  if (text.length <= max) return [text];
  const words = text.split(/\s+/);
  const lines: string[] = [''];
  for (const w of words) {
    const cur = lines[lines.length - 1] as string;
    if (cur && `${cur} ${w}`.length > max && lines.length < 2) lines.push(w);
    else lines[lines.length - 1] = cur ? `${cur} ${w}` : w;
  }
  return lines.map((l) => (l.length > max + 4 ? `${l.slice(0, max + 3)}…` : l));
};

/**
 * Step diagram drawn with SVG and design tokens (classes in Blueprint.module.css, no colour here).
 * The geometry is mirrored for right-to-left so the flow reads from the right. Edges carry numbers;
 * the numbered list under the diagram is the text equivalent, so the SVG itself is decoration.
 */
export function FlowDiagram({ flow, rtl, label }: { flow: FlowModel; rtl: boolean; label: string }) {
  const hasBack = flow.edges.some((e) => e.back);
  const width = PAD * 2 + flow.cols * W + (flow.cols - 1) * GAP_X;
  const height = PAD * 2 + flow.rows * H + (flow.rows - 1) * GAP_Y + (hasBack ? BACK : 0);
  const pos = (col: number, row: number) => ({
    x: rtl ? width - PAD - W - col * (W + GAP_X) : PAD + col * (W + GAP_X),
    y: PAD + row * (H + GAP_Y),
  });
  const at = new Map(flow.nodes.map((n) => [n.id, { ...pos(n.col, n.row), n }]));
  const mark = `arrow-${flow.id}`;
  return (
    <div className={styles.diagram} role="group" aria-label={label} tabIndex={0}>
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden="true" focusable="false" className={styles.svg}>
        <defs>
          <marker id={mark} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">
            <path d="M0 0 L10 5 L0 10 z" className={styles.arrow} />
          </marker>
        </defs>
        {flow.edges.map((e) => {
          const a = at.get(e.from);
          const b = at.get(e.to);
          if (!a || !b) return null;
          let d: string;
          let mx: number;
          let my: number;
          if (e.back) {
            const sx = a.x + W / 2;
            const tx = b.x + W / 2;
            const sy = a.y + H;
            const ty = b.y + H;
            const dip = Math.max(sy, ty) + BACK - 8;
            d = `M${sx} ${sy} C${sx} ${dip} ${tx} ${dip} ${tx} ${ty}`;
            mx = (sx + tx) / 2;
            my = dip - 2;
          } else if (a.n.col === b.n.col) {
            const down = b.y >= a.y;
            const sx = a.x + W / 2;
            const sy = down ? a.y + H : a.y;
            const ty = down ? b.y : b.y + H;
            d = `M${sx} ${sy} L${sx} ${ty}`;
            mx = sx;
            my = (sy + ty) / 2;
          } else {
            const dir = rtl ? -1 : 1;
            const sx = a.x + (rtl ? 0 : W);
            const tx = b.x + (rtl ? W : 0);
            const sy = a.y + H / 2;
            const ty = b.y + H / 2;
            const k = (Math.abs(tx - sx) / 2) * dir;
            d = `M${sx} ${sy} C${sx + k} ${sy} ${tx - k} ${ty} ${tx} ${ty}`;
            mx = (sx + tx) / 2;
            my = (sy + ty) / 2;
          }
          return (
            <g key={e.n}>
              <path d={d} className={styles.edge} markerEnd={`url(#${mark})`} />
              <circle cx={mx} cy={my} r="10" className={styles.badge} />
              <text x={mx} y={my} className={styles.badgeText} textAnchor="middle" dominantBaseline="central">
                {e.n}
              </text>
            </g>
          );
        })}
        {flow.nodes.map((n) => {
          const p = at.get(n.id);
          if (!p) return null;
          const lines = wrap(n.label);
          return (
            <g key={n.id}>
              <rect x={p.x} y={p.y} width={W} height={H} rx="8" className={`${styles.node} ${n.kind === 'initial' ? styles.nodeStart : ''} ${n.kind === 'final' ? styles.nodeEnd : ''}`} />
              <text x={p.x + W / 2} y={p.y + H / 2 - ((lines.length - 1) * 8)} className={styles.nodeText} textAnchor="middle" dominantBaseline="central">
                {lines.map((l, i) => (
                  <tspan key={i} x={p.x + W / 2} dy={i === 0 ? 0 : 16}>
                    {l}
                  </tspan>
                ))}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
