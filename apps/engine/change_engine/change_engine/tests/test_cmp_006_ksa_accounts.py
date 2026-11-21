"""Validate the Saudi trading chart and VAT data without a running bench."""

import json
import re
import unittest
from pathlib import Path

DATA = Path(__file__).resolve().parents[3] / 'compliance' / 'ksa'
NATIVE_FIELDS = {'account_number', 'root_type', 'account_type'}
LEAF_TYPES = {
    'Asset': {'Accumulated Depreciation', 'Bank', 'Capital Work in Progress', 'Cash',
              'Current Asset', 'Fixed Asset', 'Receivable', 'Stock', 'Tax', 'Temporary'},
    'Liability': {'Asset Received But Not Billed', 'Current Liability', 'Liability',
                  'Payable', 'Round Off for Opening', 'Stock Received But Not Billed', 'Tax'},
    'Equity': {'Equity'},
    'Income': {'Direct Income', 'Income Account', 'Indirect Income'},
    'Expense': {'Cost of Goods Sold', 'Depreciation', 'Expenses Included In Asset Valuation',
                'Expenses Included In Valuation', 'Indirect Expense', 'Round Off',
                'Stock Adjustment'},
}
DEFAULTS = {
    'default_cash_account': 'Cash', 'default_bank_account': 'Bank',
    'default_receivable_account': 'Receivable', 'default_payable_account': 'Payable',
    'default_inventory_account': 'Stock', 'stock_received_but_not_billed': 'Stock Received But Not Billed',
    'default_income_account': 'Income Account', 'default_expense_account': 'Cost of Goods Sold',
    'stock_adjustment_account': 'Stock Adjustment', 'expenses_included_in_valuation': 'Expenses Included In Valuation',
    'round_off_account': 'Round Off', 'round_off_for_opening': 'Round Off for Opening',
    'accumulated_depreciation_account': 'Accumulated Depreciation', 'depreciation_expense_account': 'Depreciation',
    'capital_work_in_progress_account': 'Capital Work in Progress',
    'asset_received_but_not_billed': 'Asset Received But Not Billed',
    'expenses_included_in_asset_valuation': 'Expenses Included In Asset Valuation',
    'write_off_account': 'Indirect Expense', 'exchange_gain_loss_account': 'Indirect Expense',
    'disposal_account': 'Indirect Expense',
}


def load(name):
    """Read JSON and reject duplicate keys before the decoder can discard them."""
    def unique_keys(pairs):
        result = dict(pairs)
        if len(result) != len(pairs):
            raise ValueError(f'Duplicate key in {name}')
        return result

    return json.loads((DATA / name).read_text(encoding='utf-8'), object_pairs_hook=unique_keys)


class KsaAccountsTests(unittest.TestCase):
    """Check native chart shape, bilingual data and links into posting accounts."""

    def setUp(self):
        self.chart = load('sa_trading_chart_of_accounts.json')
        self.defaults_doc = load('company_account_defaults.json')
        self.defaults = self.defaults_doc['defaults']
        self.vat = load('vat_treatments.json')
        self.numbers = set()
        self.leaves = {}
        for name, node in self.chart['tree'].items():
            self.visit(name, node, node['root_type'], at_root=True)

    def visit(self, name, node, root, *, at_root=False):
        """Walk keys as the pinned importer does and retain posting accounts by number."""
        self.assertRegex(name, r'^[\u0600-\u06ff][\u0600-\u06ff ]+ \([A-Za-z][A-Za-z &-]+\)$')
        number = node['account_number']
        self.assertRegex(number, r'^[1-5][0-9]{3}$')
        self.assertNotIn(number, self.numbers)
        self.numbers.add(number)
        children = node.keys() - NATIVE_FIELDS
        if not at_root:
            self.assertNotIn('root_type', node)
        if children:
            self.assertNotIn('account_type', node)
            for child in children:
                self.assertIsInstance(node[child], dict)
                self.visit(child, node[child], root)
        else:
            self.assertFalse(at_root)
            self.assertIn(node['account_type'], LEAF_TYPES[root])
            self.leaves[number] = (root, node['account_type'])

    def test_draft_version_and_review_metadata(self):
        for doc in (self.chart, self.defaults_doc, self.vat):
            self.assertEqual(doc['status'], 'draft')
            self.assertEqual(doc['version'], '0.1.0')
            self.assertEqual(doc['review'], 'unreviewed')

    def test_chart_has_five_native_roots_and_bilingual_accounts(self):
        self.assertEqual(set(self.chart), {'status', 'version', 'review', 'country_code', 'name', 'tree'})
        self.assertEqual(self.chart['country_code'], 'sa')
        roots = [root['root_type'] for root in self.chart['tree'].values()]
        self.assertCountEqual(roots, LEAF_TYPES.keys())

    def test_system_accounts_and_company_defaults(self):
        self.assertEqual(set(self.defaults_doc), {'status', 'version', 'review', 'defaults'})
        self.assertEqual(set(self.defaults), set(DEFAULTS))
        self.assertEqual(len(self.defaults), len(set(self.defaults.values())))
        for field, kind in DEFAULTS.items():
            self.assertEqual(self.leaves[self.defaults[field]][1], kind, field)
        self.assertEqual(self.leaves['1190'], ('Asset', 'Temporary'))
        self.assertEqual(self.leaves[self.defaults['round_off_for_opening']], ('Liability', 'Round Off for Opening'))
        self.assertEqual(self.leaves['3200'], ('Equity', 'Equity'))  # Retained earnings.

    def test_vat_categories_and_reason_codes(self):
        self.assertEqual(set(self.vat), {'status', 'version', 'review', 'invoice_categories', 'treatments'})
        categories = self.vat['invoice_categories']
        self.assertEqual({code: data['invoice_rate_percent'] for code, data in categories.items()},
                         {'S': 15, 'Z': 0, 'E': 0, 'O': None})
        self.assertEqual({code: set(data['reasons']) for code, data in categories.items()}, {
            'S': set(),
            'Z': {'VATEX-SA-32', 'VATEX-SA-33', 'VATEX-SA-34-1', 'VATEX-SA-34-2', 'VATEX-SA-34-3',
                  'VATEX-SA-34-4', 'VATEX-SA-34-5', 'VATEX-SA-35', 'VATEX-SA-36', 'VATEX-SA-EDU',
                  'VATEX-SA-HEA', 'VATEX-SA-MLTRY'},
            'E': {'VATEX-SA-29', 'VATEX-SA-29-7', 'VATEX-SA-30'},
            'O': {'VATEX-SA-OOS'},
        })
        self.assertIsNone(categories['O']['reasons']['VATEX-SA-OOS'])
        for code in ('Z', 'E'):
            for reason in categories[code]['reasons'].values():
                self.assertTrue(reason['en'])
                self.assertRegex(reason['ar'], r'[\u0600-\u06ff]')
                self.assertEqual(reason['review'], 'unreviewed')
        self.assertEqual(categories['Z']['reasons']['VATEX-SA-32']['en'], 'Export of goods')
        self.assertEqual(categories['Z']['reasons']['VATEX-SA-32']['ar'], 'صادرات السلع من المملكة')
        self.assertEqual(
            categories['E']['reasons']['VATEX-SA-29']['en'],
            'Financial services mentioned in Article 29 of the VAT Regulations',
        )

    def test_tax_templates_link_to_company_posting_accounts(self):
        expected = {
            'domestic_sale_standard': ('S', 15, 'Sales Taxes and Charges Template', {'output': '2210'}),
            'domestic_purchase_standard': (None, 15, 'Purchase Taxes and Charges Template', {'input': '1151'}),
            'sale_zero_rated': ('Z', 0, 'Sales Taxes and Charges Template', {'output': '2210'}),
            'sale_exempt': ('E', None, 'Sales Taxes and Charges Template', {'output': '2210'}),
            'sale_out_of_scope': ('O', None, None, {}),
            'goods_import_standard_at_customs': (None, 15, None, {'eligible_input': '1152'}),
            'services_reverse_charge_standard': (None, 15, None, {'eligible_input': '1153', 'output': '2220'}),
        }
        treatments = self.vat['treatments']
        self.assertEqual(set(expected), set(treatments))
        linked_accounts = set()
        for key, (category, rate, doctype, accounts) in expected.items():
            with self.subTest(treatment=key):
                data = treatments[key]
                self.assertEqual(data['review'], 'unreviewed')
                self.assertEqual(data['invoice_category'], category)
                self.assertEqual(data['vat_rate_percent'], rate)
                self.assertEqual(data['posting_accounts'], accounts)
                self.assertTrue(data['label']['en'])
                self.assertIsNotNone(re.search(r'[\u0600-\u06ff]', data['label']['ar']))
                for role, number in accounts.items():
                    root = 'Liability' if role == 'output' else 'Asset'
                    self.assertEqual(self.leaves[number], (root, 'Tax'))
                    linked_accounts.add(number)
                template = data['engine_template']
                if doctype is None:
                    self.assertIsNone(template)
                    continue
                self.assertEqual(template['doctype'], doctype)
                (row,) = template['taxes']
                self.assertEqual(row['charge_type'], 'On Net Total')
                self.assertIn(row['account_role'], accounts)
                if doctype == 'Purchase Taxes and Charges Template':
                    self.assertEqual((row['category'], row['add_deduct_tax']), ('Total', 'Add'))
                expected_rate = self.vat['invoice_categories'][category]['invoice_rate_percent'] if category else rate
                self.assertEqual(row['rate'], expected_rate)
                self.assertEqual(template['is_default'], 0)
        self.assertEqual(linked_accounts, {number for number, (_, kind) in self.leaves.items() if kind == 'Tax'})


if __name__ == '__main__':
    unittest.main()
