// Synthetic review model for the owner approval screen until the host adapters exist (Q-505, Q-544). review.json is a
// real `OwnerApproval.review` output for invented data (trimmed); the variants below change only what each case needs.
import review from './review.json';
import type { ApprovalPort, DecisionRequest, ReviewModel, SummarySection } from '../types';

export const fixtureReview = review as unknown as ReviewModel;

/** A state the model emits: the plan is too large to list, so approve is not allowed but the other two are. */
export const fixtureBlockedReview: ReviewModel = {
  ...fixtureReview,
  canDecide: true, // too_large stops an approval only; rejecting and asking for changes still work (flow.py can_change)
  blockers: [{ key: 'too_large', labelKey: 'oa.blocker.too_large' }],
  decisions: fixtureReview.decisions.map((d) => (d.key === 'approve' ? { ...d, allowed: false } : d)),
};

/** Customer-derived text that tries to become markup, a message placeholder or a bidi trick. Must render as plain text. */
export const INJECTION = '<img src=x onerror="alert(1)"> {rate} <script>alert(2)</script>';
export const fixtureInjectionReview: ReviewModel = {
  ...fixtureReview,
  sections: fixtureReview.sections.map((s) => {
    if (s.id !== 'summary') return s;
    const sum = s as SummarySection;
    return { ...sum, items: sum.items.map((it, i) => (i === 0 ? { ...it, labels: { ar: INJECTION, en: INJECTION, cut: false } } : it)) };
  }),
};

/** A fake port: records what the screen emitted and answers ok. No network. */
export function fakePort(answer: { ok: true } | { ok: false; code: string } = { ok: true }): ApprovalPort & { calls: DecisionRequest[] } {
  const calls: DecisionRequest[] = [];
  return { calls, decide: async (req) => (calls.push(req), answer) };
}
