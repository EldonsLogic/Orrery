// Synthetic rows for the screens until the gateway exists (PLT-009). Invented people and numbers; never real data.
import blueprint from './blueprint.json';
import tools from './tools.json';
import type { Caller, RecordsData } from '../types';

const m = (value: string) => ({ value, currency: 'SAR' });

export const fixtureData: RecordsData = {
  entities: blueprint.entities,
  workflows: blueprint.workflows,
  tools: tools.tools as unknown as RecordsData['tools'],
  rows: {
    customer: [
      { id: 'CUST-001', customer_name: 'Sample Trading Co', vat_number: '300000000000003', phone: '+966500000001', credit_limit: m('50000.00') },
      { id: 'CUST-002', customer_name: 'Example Foods', vat_number: '300000000000011', phone: '+966500000002', credit_limit: m('12000.00') },
      { id: 'CUST-003', customer_name: 'Demo Stores', phone: '+966500000003', credit_limit: m('8000.00') },
    ],
    item: [
      { id: 'ITM-001', item_code: 'RICE-5', item_name: 'Rice 5 kg', unit: 'piece', selling_price: m('24.50') },
      { id: 'ITM-002', item_code: 'OIL-12', item_name: 'Cooking oil carton', unit: 'carton', selling_price: m('96.00') },
    ],
    sales_order: [
      { id: 'SO-00001', state: 'draft', customer: 'CUST-001', order_date: '2026-03-01', subtotal: m('1000.00'), vat_amount: m('150.00'), total_amount: m('1150.00') },
      { id: 'SO-00002', state: 'pending_approval', customer: 'CUST-002', order_date: '2026-03-02', subtotal: m('61200.00'), vat_amount: m('9180.00'), total_amount: m('70380.00') },
      { id: 'SO-00003', state: 'approved', customer: 'CUST-001', order_date: '2026-03-03', subtotal: m('400.00'), vat_amount: m('60.00'), total_amount: m('460.00') },
      { id: 'SO-00004', state: 'delivered', customer: 'CUST-003', order_date: '2026-03-04', subtotal: m('250.00'), vat_amount: m('37.50'), total_amount: m('287.50') },
      { id: 'SO-00005', state: 'cancelled', customer: 'CUST-003', order_date: '2026-03-05', subtotal: m('90.00'), vat_amount: m('13.50'), total_amount: m('103.50') },
      { id: 'SO-00006', state: 'draft', customer: 'CUST-002', order_date: '2026-03-06', subtotal: m('300.00'), vat_amount: m('45.00'), total_amount: m('345.00') },
    ],
    sales_invoice: [
      { id: 'INV-00001', customer: 'CUST-001', invoice_date: '2026-03-10', total_amount: m('1150.00') },
    ],
  },
};

/** Placeholder caller until identity (PLT-005): passed to the screens as data, never read from the browser. */
export const fixtureCaller: Caller = { roleIds: ['sales_rep'] };
