import { can } from '../console/access';
import type { StaffRole } from '../console/types';
import { REQUEST_STATUSES, type ComponentRequestRecord, type RequestStatus, type ReviewAction, type RiskClass } from './types';

export type DisabledReason =
  | 'no_permission'
  | 'wrong_status'
  | 'separation'
  | 'money_field'
  | 'needs_attestation'
  | 'no_generalisation';

export type ActionState = { enabled: true } | { enabled: false; reason: DisabledReason };

export type Reviewer = { staffId: string; roles: ReadonlyArray<StaffRole> };

const STATUS_FOR: Record<ReviewAction, ReadonlyArray<RequestStatus>> = {
  attest_risk_class: ['needs_human_classification'],
  attest_generalisable: ['drafted', 'in_review'],
  approve: ['in_review'],
  reject: ['in_review'],
};

const lower = (v: string | null | undefined) => (typeof v === 'string' ? v.toLowerCase() : '');

/** Distinct tenants with at least one evidence item (a tenant without evidence does not count). */
export const evidencedTenants = (r: ComponentRequestRecord): number =>
  Object.values(r.tenants ?? {}).filter((ev) => Array.isArray(ev) && ev.length > 0).length;

/**
 * Whether the current staff user is OFFERED an action. This mirrors the server's rules (pipeline.py `_human`, `_verify`) so
 * the button can say why it is off, but it is a convenience only: the server decides, and a button that is on can still be
 * refused. Deny by default: anything not clearly allowed is off. Order of reasons: permission, status, separation of
 * duties, then the action's own preconditions.
 */
export function actionState(
  record: ComponentRequestRecord,
  reviewer: Reviewer,
  action: ReviewAction,
  minTenants: number,
  riskClass?: RiskClass,
): ActionState {
  const off = (reason: DisabledReason): ActionState => ({ enabled: false, reason });
  if (!can(reviewer.roles, 'factory.review')) return off('no_permission');
  if (!STATUS_FOR[action].includes(record.status)) return off('wrong_status');
  const me = lower(reviewer.staffId);
  const barred = [record.requested_by, record.drafted_by, record.submitted_by];
  if (action === 'approve') {
    const c = record.classification;
    barred.push(c?.need_attested_by, c?.draft_attested_by, record.generalisation?.attested_by);
  }
  if (!me || barred.some((b) => lower(b) === me)) return off('separation');
  if (action === 'attest_risk_class' && riskClass === 'plain' && record.draft && record.classification?.draft?.has_money_field)
    return off('money_field');
  if (action === 'approve') {
    const d = record.classification?.draft;
    if (d && !d.proven && (!record.draft_digest || record.classification.draft_attested_digest !== record.draft_digest))
      return off('needs_attestation');
    if (evidencedTenants(record) < minTenants && !record.generalisation?.attested_by) return off('no_generalisation');
  }
  return { enabled: true };
}

export function countByStatus(records: ReadonlyArray<ComponentRequestRecord>): Record<RequestStatus, number> {
  const out = Object.fromEntries(REQUEST_STATUSES.map((s) => [s, 0])) as Record<RequestStatus, number>;
  for (const r of records) if (r.status in out) out[r.status] += 1;
  return out;
}

export function filterByStatus(records: ReadonlyArray<ComponentRequestRecord>, status: RequestStatus | ''): ComponentRequestRecord[] {
  return records.filter((r) => status === '' || r.status === status);
}

export const statusTone = (s: string): 'success' | 'warning' | 'danger' | 'neutral' =>
  s === 'approved' ? 'success' : s === 'in_review' || s === 'needs_human_classification' || s === 'drafted' ? 'warning' : s === 'rejected' || s === 'refused' || s === 'drafting_failed' ? 'danger' : 'neutral';
