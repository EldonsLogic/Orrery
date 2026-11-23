// The DSC-009 owner-approval view model (services/discovery/owner_approval, `OwnerApproval.review`) as the screen
// reads it. Every sentence is a label key; every field marked untrustedText is customer or document text and is
// only ever rendered as plain text. Numbers (money, counts) arrive finished: the screen never adds or rounds.
export type Loc = { ar: string; en: string; cut: boolean };
export type Money = { minor: number; currency: string; exponent: number; text: string };
export type LabelRef = { key: string; labelKey: string };

export type SummaryItem = { kind: string; kindKey: string; id: string; labels: Loc; details?: Detail; untrustedText: true };
export type Detail = { [k: string]: string | number | boolean | null | Detail | ReadonlyArray<string | number | boolean | null | Detail> };
export type SummarySection = {
  id: 'summary'; labelKey: string; introKey: string;
  company: { legalName: Loc; legalNameKey: string; tradeName: Loc | null; tradeNameKey: string; country: string };
  notShown: ReadonlyArray<{ key: string; labelKey: string }>; notShownNoticeKey: string;
  items: ReadonlyArray<SummaryItem>; moreItems: number;
};
export type QuoteLine = { id: string; labelKey: string; params: Readonly<Record<string, string>>; quantity: number; unit: Money; total: Money };
export type Totals = { subtotal: Money; tax: Money; taxRateBp: number; total: Money };
export type CostSection = {
  id: 'cost'; labelKey: string; currency: string;
  lines: { recurring: ReadonlyArray<QuoteLine>; one_off: ReadonlyArray<QuoteLine> };
  totals: { recurring: Totals; one_off: Totals };
  unpriced: ReadonlyArray<{ requirement: string }>; validUntil: string; quoteState: string; noticeKey: string; notes: ReadonlyArray<string>;
};
export type GapsSection = {
  id: 'gaps'; labelKey: string; counts: { covered: number; partial: number; uncovered: number };
  items: ReadonlyArray<{ kindKey: string; status: string; statusKey: string; ref: string }>; moreItems: number; noneKey: string | null;
};
export type SimulationSection = { id: 'simulation'; labelKey: string; introKey: string; checks: ReadonlyArray<LabelRef>; noticeKey: string };
export type Section = SummarySection | CostSection | GapsSection | SimulationSection;

export type DecisionKey = 'approve' | 'request_changes' | 'reject';
export type DecisionOption = {
  key: DecisionKey; labelKey: string; noteRequired: boolean; allowed: boolean;
  reasons: ReadonlyArray<{ value: string; labelKey: string }>;
};
export type ReviewModel = {
  schema: string; titleKey: string; introKey: string; tenantId: string; blueprintId: string; revision: number;
  blueprintDigest: string; quoteDigest: string; buildStateKey: string; state: { value: string; labelKey: string };
  sections: ReadonlyArray<Section>; confirmations: ReadonlyArray<LabelRef>; decisions: ReadonlyArray<DecisionOption>;
  canDecide: boolean; blockers: ReadonlyArray<{ key: string; labelKey: string }>; noteLimit: number;
  stepUpNoticeKey: string; evidenceNoticeKey: string; commitNoticeKey: string;
  history: ReadonlyArray<{ seq: number; decision: string; decisionKey: string; reasonKey: string; note: string; at: number | string; stale: boolean }>;
};

/** What the screen emits. The host adapter (Q-505) adds the owner's claims and step-up; the screen never sees them. */
export type DecisionRequest = {
  tenantId: string; blueprintId: string; decision: DecisionKey; reason: string; note: string;
  seenBlueprintDigest: string; seenQuoteDigest: string; confirmations: ReadonlyArray<string>;
};
export type DecisionResult = { ok: true } | { ok: false; code: string };
/** The only way out of the screen. No network here: the live adapter waits for Q-544 and Q-505. */
export type ApprovalPort = { decide: (req: DecisionRequest) => Promise<DecisionResult> };
