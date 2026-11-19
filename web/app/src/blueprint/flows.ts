// Step diagram layout for one workflow. Pure: columns are the steps' distance from the start, rows are
// the order inside a column. Drawing (and mirroring for right-to-left) is the component's job.
import type { BpWorkflow, FlowEdge, FlowNode } from './types';

export type FlowLayout = { nodes: ReadonlyArray<FlowNode>; edges: ReadonlyArray<FlowEdge>; cols: number; rows: number };

export function layoutFlow(wf: BpWorkflow, labelOf: (l: BpWorkflow['states'][number]['labels'], id: string) => string): FlowLayout {
  const depth = new Map<string, number>();
  const start = wf.states.filter((s) => s.kind === 'initial');
  const queue = (start.length > 0 ? start : wf.states.slice(0, 1)).map((s) => s.id);
  queue.forEach((id) => depth.set(id, 0));
  for (let i = 0; i < queue.length; i++) {
    const id = queue[i] as string;
    for (const t of wf.transitions) {
      if (t.from === id && !depth.has(t.to)) {
        depth.set(t.to, (depth.get(id) ?? 0) + 1);
        queue.push(t.to);
      }
    }
  }
  const maxDepth = Math.max(0, ...depth.values());
  const rowsIn = new Map<number, number>();
  const nodes: FlowNode[] = wf.states.map((s) => {
    const col = depth.get(s.id) ?? maxDepth + 1; // unreachable steps go last
    const row = rowsIn.get(col) ?? 0;
    rowsIn.set(col, row + 1);
    const kind = s.kind === 'initial' ? 'initial' : s.kind === 'final' ? 'final' : 'normal';
    return { id: s.id, label: labelOf(s.labels, s.id), kind, locked: s.locksEditing === true, col, row };
  });
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const edges: FlowEdge[] = wf.transitions.flatMap((t, i) => {
    const a = byId.get(t.from);
    const b = byId.get(t.to);
    return a && b ? [{ n: i + 1, from: t.from, to: t.to, back: b.col < a.col }] : [];
  });
  return { nodes, edges, cols: Math.max(...nodes.map((n) => n.col), 0) + 1, rows: Math.max(...rowsIn.values(), 1) };
}
