/**
 * Types for the component factory review screens (PLT-014). They mirror the component request record of
 * services/blueprint/component_request (BPL-016) MINUS the seal, key ids and digests that only the server may judge.
 * Everything in a record can come from a model or from a tenant's conversation, so every string is UNTRUSTED: it is
 * only ever shown as plain text (see text.ts), never as HTML, never as a link target, never evaluated.
 */
export const REQUEST_STATUSES = [
  'requested',
  'needs_human_classification',
  'drafted',
  'in_review',
  'approved',
  'rejected',
  'refused',
  'drafting_failed',
] as const;
export type RequestStatus = (typeof REQUEST_STATUSES)[number];

export const RISK_CLASSES = ['plain', 'stock', 'ledger', 'tax', 'permission'] as const;
export type RiskClass = (typeof RISK_CLASSES)[number];

export const REJECT_REASONS = ['not_generalisable', 'duplicate', 'out_of_scope', 'quality', 'other'] as const;
export type RejectReason = (typeof REJECT_REASONS)[number];

export type Evidence = { kind: string; id: string };

export type HistoryEvent = {
  seq: number;
  at: string;
  actor: string;
  actor_kind: string;
  event: string;
  from: string | null;
  to: string;
  code: string | null;
  detail: Record<string, unknown>;
};

export type DraftField = { entity: string; name: string; type: string; required?: boolean; options?: ReadonlyArray<string>; target?: string };

export type RequestDraft = {
  manifest: {
    id: string;
    version: string;
    name: { ar: string; en: string };
    description: string;
    provides: ReadonlyArray<{ capability: string; artifacts: ReadonlyArray<{ type: string; ref: string }> }>;
    tests: ReadonlyArray<{ id: string; kind: string; path: string; blocking: boolean }>;
  };
  spec: {
    capabilities: ReadonlyArray<{ id: string; summary: string }>;
    fields: ReadonlyArray<DraftField>;
    permissions: ReadonlyArray<{ role: string; action: string }>;
    i18n_keys: ReadonlyArray<string>;
    test_plan: ReadonlyArray<{ id: string; kind: string; covers: ReadonlyArray<string> | string; blocking: boolean }>;
  };
  /** The model's rationale is display text only; it proves nothing (BPL-016 rule). */
  generalisation: { rationale: string; tenant_specific: boolean };
};

export type DraftClassification = { proven: boolean; reasons: ReadonlyArray<string>; has_money_field: boolean };

export type ComponentRequestRecord = {
  id: string;
  status: RequestStatus;
  need: { kind: string; ref: string; kind_hint: string };
  /** Opaque tenant reference (a hash, never a name) to that tenant's evidence items. Never merged across tenants. */
  tenants: Readonly<Record<string, ReadonlyArray<Evidence>>>;
  flags: ReadonlyArray<string>;
  requested_by: string;
  created_at: string;
  draft: RequestDraft | null;
  draft_digest: string | null;
  drafted_by: string | null;
  submitted_by: string | null;
  generalisation: { attested_by: string | null; attested_at: string | null };
  classification: {
    need_attested_by: string | null;
    need_attested_at: string | null;
    draft: DraftClassification | null;
    draft_attested_by: string | null;
    draft_attested_at: string | null;
    draft_attested_digest: string | null;
  };
  refusal: { code: string; route: string } | null;
  decision: { by: string; at: string; outcome: string; reason?: string } | null;
  history: ReadonlyArray<HistoryEvent>;
};

export type ReviewAction = 'attest_risk_class' | 'attest_generalisable' | 'approve' | 'reject';

export type ReviewCommand = {
  requestId: string;
  action: ReviewAction;
  /** Only for attest_risk_class. */
  riskClass?: RiskClass;
  /** Only for reject. */
  reason?: RejectReason;
};
