// Action model: which writes the UI may offer and how. Risk class decides the mode (WEB-023).
//   R0/R1 -> direct. R2 -> confirm (summary first). R3/R4 or agent_creatable=false -> needs_approval (never executed).
import { roleAllows, toolFor, usable } from './access';
import type { ActionKind, ActionMode, Caller, EntityDef, Loc, RecordRow, RiskClass, ToolDef, TransitionDef, WorkflowDef } from './types';

export type ActionModel = {
  id: string; // stable key: kind or kind:transition id
  kind: ActionKind;
  tool: string;
  transitionId?: string;
  risk: RiskClass;
  mode: ActionMode;
  labels?: Loc; // from the tool or transition; absent means the screen uses its own generic label for the kind
  effects: { ledger: boolean; tax: boolean; externalSend: boolean };
};

export const modeFor = (risk: RiskClass, agentCreatable: boolean): ActionMode =>
  risk === 'R3' || risk === 'R4' || !agentCreatable ? 'needs_approval' : risk === 'R2' ? 'confirm' : 'direct';

export const executable = (a: Pick<ActionModel, 'mode'>): boolean => a.mode !== 'needs_approval';

const fx = (t: ToolDef) => ({ ledger: !!t.effects?.ledger, tax: !!t.effects?.tax, externalSend: !!t.effects?.external_send });

const fromTool = (kind: ActionKind, t: ToolDef): ActionModel => ({
  id: kind, kind, tool: t.name, risk: t.risk_class, mode: modeFor(t.risk_class, t.agent_creatable), effects: fx(t),
});

const fromTransition = (kind: ActionKind, t: ToolDef, tr: TransitionDef): ActionModel => ({
  id: `${kind}:${tr.id}`, kind, tool: t.name, transitionId: tr.id, risk: tr.risk_class,
  mode: modeFor(tr.risk_class, tr.agent_creatable && t.agent_creatable), labels: tr.labels, effects: fx(t),
});

const CANCEL_KINDS = new Set(['cancel', 'cancel_draft']);

export type ActionContext = {
  entity: EntityDef;
  workflow?: WorkflowDef;
  tools: ReadonlyArray<ToolDef>;
  caller: Caller;
  /** The record being viewed; absent on the create screen and on lists. */
  record?: RecordRow;
};

/**
 * Everything the caller may be offered for this entity (and record). Anything the tool set does not allow is absent.
 * `amend` exists only if an `<entity>.amend` tool exists; there is none in today's generator, so it never shows.
 */
export function buildActions({ entity, workflow, tools, caller, record }: ActionContext): ActionModel[] {
  const out: ActionModel[] = [];
  const state = record ? workflow?.states.find((s) => s.id === record.state) : undefined;
  const locked = !!state?.locksEditing || state?.kind === 'final';
  const one = (verb: string) => {
    const t = toolFor(tools, entity.id, verb);
    return usable(t, caller) ? t : undefined;
  };
  if (!record) {
    const c = one('create');
    if (c) out.push(fromTool('create', c));
    return out;
  }
  const u = one('update');
  if (u && !locked) out.push(fromTool('edit', u));
  const am = one('amend');
  if (am && locked) out.push(fromTool('amend', am));
  const sub = one('submit');
  if (sub) out.push(fromTool('submit', sub));
  const cancel = one('cancel');
  if (cancel) out.push(fromTool('cancel', cancel));
  const tt = one('transition');
  for (const tr of tt?.transitions ?? []) {
    if (tr.from !== record.state || !roleAllows(tr.allowed_roles, caller)) continue;
    const kind: ActionKind = CANCEL_KINDS.has(tr.kind) ? 'cancel' : tr.kind === 'advance' ? 'submit' : 'transition';
    out.push(fromTransition(kind, tt!, tr));
  }
  return out;
}

export type Change = { fieldId: string; before: string; after: string };

/** What will change, for the confirm step. Only fields whose text differs; never includes hidden fields (the form model drops them). */
export function summarizeChanges(
  fieldIds: ReadonlyArray<string>,
  before: Readonly<Record<string, string>>,
  after: Readonly<Record<string, string>>,
): Change[] {
  return fieldIds
    .filter((id) => (before[id] ?? '') !== (after[id] ?? ''))
    .map((id) => ({ fieldId: id, before: before[id] ?? '', after: after[id] ?? '' }));
}
