// Synthetic figures for two invented trading companies. No real company, person or figure.
import type { HomeOverview } from './types';

const SAR = 'SAR';

export const liveHome: HomeOverview = {
  asOf: '2026-11-26',
  buildState: 'live',
  simulated: false,
  today: {
    deliveries: 3,
    collections: { count: 5, amount: 64300, currency: SAR },
    payments: { count: 2, amount: 21050, currency: SAR },
  },
  kpis: [
    { id: 'sales_month', value: { amount: 482350, currency: SAR }, change: 12.4, trend: [361200, 392800, 377400, 405900, 429100, 482350] },
    { id: 'receivables', value: { amount: 216480, currency: SAR }, overdue: 3 },
    { id: 'awaiting_approval', value: { count: 4 }, oldestDays: 2 },
    { id: 'cash', value: { amount: 1204880, currency: SAR }, change: -3.1, trend: [1068400, 1121700, 1159300, 1187600, 1243400, 1204880] },
  ],
  approvals: [
    {
      id: 'ap-1',
      kind: 'purchase_order',
      ref: 'PO-0142',
      party: { en: 'Gulf Packaging Supplies', ar: 'مؤسسة الخليج لمواد التغليف' },
      amount: { amount: 38400, currency: SAR },
      reason: { en: 'Carton stock is below the reorder level', ar: 'مخزون الكراتين أقل من حد إعادة الطلب' },
    },
    {
      id: 'ap-2',
      kind: 'supplier_payment',
      ref: 'PAY-0087',
      party: { en: 'Al Noor Logistics', ar: 'النور للخدمات اللوجستية' },
      amount: { amount: 12750, currency: SAR },
      reason: { en: 'Invoice due on 28 November', ar: 'الفاتورة مستحقة في 28 نوفمبر' },
    },
    {
      id: 'ap-3',
      kind: 'discount',
      ref: 'SO-0311',
      party: { en: 'Jeddah Fresh Mart', ar: 'جدة فريش مارت' },
      amount: { amount: 6900, currency: SAR },
      reason: { en: '8% volume discount on a repeat order', ar: 'خصم كمية 8% على طلب متكرر' },
    },
    {
      id: 'ap-4',
      kind: 'credit_note',
      ref: 'CN-0019',
      party: { en: 'Riyadh Home Market', ar: 'سوق الرياض المنزلي' },
      amount: { amount: 2310, currency: SAR },
      reason: { en: 'Damaged goods returned', ar: 'بضاعة تالفة مرتجعة' },
    },
  ],
  activity: [
    { id: 'ac-1', kind: 'invoice_paid', at: '2026-11-26T09:42:00Z', ref: 'INV-0459', party: { en: 'Riyadh Home Market', ar: 'سوق الرياض المنزلي' }, amount: { amount: 18200, currency: SAR } },
    { id: 'ac-2', kind: 'drafted', at: '2026-11-26T08:50:00Z', count: 2 },
    { id: 'ac-3', kind: 'approved', at: '2026-11-26T08:12:00Z', ref: 'PO-0139' },
    { id: 'ac-4', kind: 'stock_low', at: '2026-11-25T17:20:00Z', party: { en: 'Olive oil, 1 litre', ar: 'زيت زيتون، 1 لتر' } },
    { id: 'ac-5', kind: 'order_created', at: '2026-11-25T15:05:00Z', ref: 'SO-0312', party: { en: 'Jeddah Fresh Mart', ar: 'جدة فريش مارت' }, amount: { amount: 24600, currency: SAR } },
  ],
};

/** A company still in its simulated month: the journey shows instead of today, and the figures are labelled simulated. */
export const simulatingHome: HomeOverview = {
  ...liveHome,
  buildState: 'built_in_sandbox',
  simulated: true,
  today: null,
  approvals: liveHome.approvals.slice(0, 2),
};
