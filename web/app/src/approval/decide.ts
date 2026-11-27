// Pure decision logic for the owner approval screen: what may be sent, and the one call through the port.
import type { ApprovalPort, DecisionKey, DecisionRequest, DecisionResult, ReviewModel } from './types';

/** `for` is the view the ticks were made against; a form made for another view never sends. */
export type Form = { for: string; decision: DecisionKey; reason: string; note: string; confirmed: ReadonlyArray<string> };

export const formKey = (view: ReviewModel): string => `${view.blueprintDigest}:${view.quoteDigest}`;
export const emptyForm = (view: ReviewModel, decision: DecisionKey): Form => {
  const o = view.decisions.find((d) => d.key === decision);
  return { for: formKey(view), decision, reason: o && o.reasons.length === 1 ? o.reasons[0].value : '', note: '', confirmed: [] };
};

export type Status = { kind: 'idle' } | { kind: 'sending' } | { kind: 'done' } | { kind: 'error'; code: string } | { kind: 'stale' };
/** Only an ok result is "recorded". OA-006 (the draft or quote moved on) locks the form: the owner must reload and read again. */
export const nextStatus = (res: DecisionResult): Status =>
  res.ok ? { kind: 'done' } : res.code === 'OA-006' ? { kind: 'stale' } : { kind: 'error', code: res.code };

/** The request for a form, or null when it must not be sent. The model decides what is allowed; nothing is invented here. */
export function buildRequest(view: ReviewModel, form: Form): DecisionRequest | null {
  if (form.for !== formKey(view)) return null;
  const opt = view.decisions.find((d) => d.key === form.decision);
  if (!opt || !opt.allowed || (form.decision === 'approve' && !view.canDecide)) return null;
  if (!opt.reasons.some((r) => r.value === form.reason)) return null;
  if (form.note.length > view.noteLimit || (opt.noteRequired && form.note.trim() === '')) return null;
  // Q-585: the three read confirmations are required to approve only; reject and request changes need none.
  const need = form.decision === 'approve' ? view.confirmations.map((c) => c.key) : [];
  if (need.some((k) => !form.confirmed.includes(k))) return null;
  return {
    tenantId: view.tenantId, blueprintId: view.blueprintId, decision: form.decision, reason: form.reason, note: form.note,
    seenBlueprintDigest: view.blueprintDigest, seenQuoteDigest: view.quoteDigest, confirmations: need,
  };
}

/** One call through the port. A refused request or a port failure is a failed result, never a thrown error. */
export async function submitDecision(port: ApprovalPort, view: ReviewModel, form: Form): Promise<DecisionResult> {
  const req = buildRequest(view, form);
  if (!req) return { ok: false, code: 'OA-001' };
  try {
    return await port.decide(req);
  } catch {
    return { ok: false, code: 'generic' };
  }
}
