// Pending changes summary. Input is the operations list of a Blueprint diff (services/blueprint/diff).
// The diff's seven impact classes fold into the four an owner cares about:
//   cosmetic, branding -> cosmetic      config, data_shape, destructive -> process
//   access             -> access        compliance, guard or tax or price edits -> money
// Counts come from code; nothing here is prose.
import { pick } from './format';
import { msg, type DiffOp, type Msg, type PendingGroup } from './types';

const KINDS = new Set(['entity', 'field', 'relation', 'workflow', 'state', 'transition', 'role', 'permission', 'approval', 'report', 'integration', 'location', 'company', 'compliance', 'branding', 'assistant']);
const MONEY_PATH = /(^|\/)(compliance|guards|conditions|vat|price|amount|credit|numbering)(\/|$)/i;

export type PendingClass = PendingGroup['cls'];

export function classOf(op: DiffOp): PendingClass {
  if (op.impact === 'access') return 'access';
  if (op.impact === 'compliance' || MONEY_PATH.test(op.schemaPath)) return 'money';
  if (op.impact === 'cosmetic' || op.impact === 'branding') return 'cosmetic';
  return 'process';
}

const ORDER: ReadonlyArray<PendingClass> = ['money', 'access', 'process', 'cosmetic'];

export function summarisePending(ops: ReadonlyArray<DiffOp>, locale: string): { total: number; groups: ReadonlyArray<PendingGroup> } {
  const groups = ORDER.map((cls): PendingGroup => {
    const mine = ops.filter((o) => classOf(o) === cls);
    const items: Msg[] = mine.map((o) =>
      msg(`pending.op.${o.op}`, {
        kind: msg(`pending.kind.${KINDS.has(o.subject.kind) ? o.subject.kind : 'other'}`),
        name: pick(o.labels?.after ?? o.labels?.before ?? undefined, locale, o.subject.id),
      }),
    );
    return { cls, count: mine.length, items };
  });
  return { total: ops.length, groups: groups.filter((g) => g.count > 0) };
}
