// Owner home view-model (WEB-029). Numbers come from code (the metrics layer later), words from i18n.
import type { Locale } from '../i18n';

export type LocalText = Readonly<Record<Locale, string>>;
export type Money = { amount: number; currency: string };

export type KpiId = 'sales_month' | 'receivables' | 'awaiting_approval' | 'cash';
export type Kpi = {
  id: KpiId;
  value: Money | { count: number };
  /** Signed percent against last month; the word (up, down) comes from i18n, never colour alone. */
  change?: number;
  /** Items that need attention, shown with the warning icon and a word. */
  overdue?: number;
  /** Days the oldest item has waited. */
  oldestDays?: number;
};

export type ApprovalKind = 'purchase_order' | 'supplier_payment' | 'credit_note' | 'discount';
/** Drafted by Seshna, waiting for a person: nothing posts until someone approves. */
export type Approval = { id: string; kind: ApprovalKind; ref: string; party: LocalText; amount: Money; reason: LocalText };

export type ActivityKind = 'invoice_paid' | 'approved' | 'drafted' | 'stock_low' | 'order_created';
export type Activity = {
  id: string;
  kind: ActivityKind;
  /** ISO time in UTC. */
  at: string;
  ref?: string;
  party?: LocalText;
  amount?: Money;
  count?: number;
};

export type TodayFacts = { deliveries: number; collections: Money & { count: number }; payments: Money & { count: number } };

export type HomeOverview = {
  /** ISO date the figures are for. */
  asOf: string;
  /** BPL-020 build state; 'live' shows today, anything else shows the journey. */
  buildState: string;
  /** Set while the figures come from the simulated month. */
  simulated: boolean;
  today: TodayFacts | null;
  kpis: ReadonlyArray<Kpi>;
  approvals: ReadonlyArray<Approval>;
  activity: ReadonlyArray<Activity>;
};
