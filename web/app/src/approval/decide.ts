// Pure decision logic for the owner approval screen: what may be sent, and the one call through the port.
import type { ApprovalPort, DecisionKey, DecisionRequest, DecisionResult, ReviewModel } from './types';

export type Form = { decision: DecisionKey; reason: string; note: string; confirmed: ReadonlyArray<string> };

/** The request for a form, or null when it must not be sent. The model decides what is allowed; nothing is invented here. */
export function buildRequest(view: ReviewModel, form: Form): DecisionRequest | null {
  const opt = view.decisions.find((d) => d.key === form.decision);
  if (!opt || !opt.allowed || (form.decision === 'approve' && !view.canDecide)) return null;
  if (!opt.reasons.some((r) => r.value === form.reason)) return null;
  if (form.note.length > view.noteLimit || (opt.noteRequired && form.note.trim() === '')) return null;
  // Q-526: never a decision without all three read confirmations.
  const need = view.confirmations.map((c) => c.key);
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
