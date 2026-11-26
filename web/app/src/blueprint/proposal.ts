// WEB-029: what the owner reviews around the Blueprint document: the modules it is built from, the gaps no module covers,
// and the draft price. Pure. The shape follows the DSC-009 review sections (what we build, what it costs, what is not
// covered); the data is a fixture until the gateway serves that view (WEB-027, Q-683). Amounts are the quote's decimal
// strings, shown as given: nothing here adds, rounds or works out tax (numbers come from code, in the quote service).
import { pick } from './format';
import type { Loc } from './types';

export type ModuleStatus = 'drafted' | 'approved';
export type GapStatus = 'uncovered' | 'partial';
export type GapKind = 'compliance' | 'component' | 'entity' | 'workflow' | 'report' | 'other';
export type ModuleIcon = 'receipt' | 'package' | 'cart' | 'file' | 'settings' | 'users' | 'workflow';

export type ProposalModule = { id: string; labels: Loc; summary: Loc; icon: ModuleIcon; status: ModuleStatus };
export type ProposalGap = { id: string; kind: GapKind; status: GapStatus; labels: Loc; plan: Loc };
export type PriceLine = { id: string; labels: Loc; amount: string };
export type PriceBlock = { lines: ReadonlyArray<PriceLine>; subtotal: string; vat: string; total: string };
export type Proposal = {
  modules: ReadonlyArray<ProposalModule>;
  gaps: ReadonlyArray<ProposalGap>;
  price: { currency: string; vatRatePercent: string; monthly: PriceBlock; oneOff: PriceBlock };
};

export type Money = { value: string; currency: string };
export type PriceBlockView = { lines: ReadonlyArray<{ id: string; label: string; amount: Money }>; subtotal: Money; vat: Money; total: Money };
export type ProposalView = {
  modules: ReadonlyArray<{ id: string; label: string; summary: string; icon: ModuleIcon; status: ModuleStatus }>;
  approved: number;
  gaps: ReadonlyArray<{ id: string; kind: GapKind; status: GapStatus; label: string; plan: string }>;
  /** Null when any figure is missing or not a plain decimal: the screen then says the price is being checked (fail closed). */
  price: { currency: string; vatRate: string; monthly: PriceBlockView; oneOff: PriceBlockView } | null;
};

export const CONFIRMATIONS = ['summary', 'quote', 'gaps'] as const;
export type Confirmation = (typeof CONFIRMATIONS)[number];

/** Approve stays closed until the owner ticked that they read what is built, the price and what is not covered (DSC-009). */
export const canApprove = (confirmed: ReadonlySet<string>): boolean => CONFIRMATIONS.every((c) => confirmed.has(c));

const DECIMAL = /^\d+(\.\d{1,3})?$/;
const ORDER: Readonly<Record<GapStatus, number>> = { uncovered: 0, partial: 1 };

function blockView(b: PriceBlock, currency: string, locale: string): PriceBlockView | null {
  const figures = [b.subtotal, b.vat, b.total, ...b.lines.map((l) => l.amount)];
  if (!figures.every((f) => DECIMAL.test(f))) return null;
  const m = (value: string): Money => ({ value, currency });
  return { lines: b.lines.map((l) => ({ id: l.id, label: pick(l.labels, locale, ''), amount: m(l.amount) })), subtotal: m(b.subtotal), vat: m(b.vat), total: m(b.total) };
}

export function buildProposalView(p: Proposal, locale: string): ProposalView {
  const monthly = blockView(p.price.monthly, p.price.currency, locale);
  const oneOff = blockView(p.price.oneOff, p.price.currency, locale);
  return {
    // A missing label shows as empty, never as the internal id.
    modules: p.modules.map((m) => ({ id: m.id, label: pick(m.labels, locale, ''), summary: pick(m.summary, locale, ''), icon: m.icon, status: m.status })),
    approved: p.modules.filter((m) => m.status === 'approved').length,
    gaps: [...p.gaps]
      .sort((a, b) => ORDER[a.status] - ORDER[b.status])
      .map((g) => ({ id: g.id, kind: g.kind, status: g.status, label: pick(g.labels, locale, ''), plan: pick(g.plan, locale, '') })),
    price: monthly && oneOff && DECIMAL.test(p.price.vatRatePercent) ? { currency: p.price.currency, vatRate: p.price.vatRatePercent, monthly, oneOff } : null,
  };
}
