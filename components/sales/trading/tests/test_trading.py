"""Native document boundary tests; the engine double enforces document permissions."""
from copy import deepcopy

import pytest

from trading import TradingPack, TradingError


class Doc:
    """Small stateful document double; no calculation or permission bypass support."""

    def __init__(self, engine, **values):
        self.engine = engine
        self.values = values

    def get(self, key):
        return self.values.get(key)

    @property
    def name(self):
        return self.get('name') or 'new-record'

    def check_permission(self, action):
        if (self.get('doctype'), self.name, action) in self.engine.denied:
            raise PermissionError(action)

    def has_permlevel_access_to(self, fieldname, df=None, permission_type='read'):
        return (self.get('doctype'), self.name, permission_type + ':' + fieldname) not in self.engine.denied

    def update(self, values):
        self.values.update(values)

    def set(self, key, value):
        self.values[key] = value

    def append(self, key, value):
        self.values.setdefault(key, []).append(value)

    def save(self):
        self.check_permission('write')
        self.engine.saved.append(deepcopy(self.values))
        return self

    def insert(self):
        self.check_permission('create')
        self.engine.saved.append(deepcopy(self.values))
        return self


class Context:
    """Independent request-context double."""

    site = 'synthetic-a'
    user = 'synthetic-user'


class Engine:
    """A site-local store which returns detached documents like a database reload."""

    def __init__(self):
        self.local = Context()
        self.session = Context()
        self.saved, self.denied, self.rows = [], set(), {}
        for dt, name, values in [
            ('Currency', 'QAR', {}), ('UOM', 'Unit', {}), ('Item', 'demo-item', {}),
            ('Company', 'demo-company', {'default_currency': 'QAR'}),
            ('Price List', 'Wholesale', {'selling': 1, 'enabled': 1, 'currency': 'QAR'}),
            ('Selling Settings', 'Selling Settings', {'editable_price_list_rate': 0}),
            ('Customer', 'demo-customer', {'credit_limits': [
                {'company': 'other-company', 'credit_limit': '40', 'bypass_credit_limit_check': 0}]}),
            ('Sales Person', 'demo-rep', {'enabled': 1, 'is_group': 0, 'commission_rate': '3'}),
            ('Sales Order', 'demo-order', {'docstatus': 0, 'company': 'demo-company'}),
        ]:
            self.rows[dt, name] = dict(doctype=dt, name=name, **values)

    def get_meta(self, doctype):
        return self

    def get_field(self, name):
        return name

    def get_doc(self, doctype, name):
        return Doc(self, **deepcopy(self.rows[doctype, name]))

    def new_doc(self, doctype):
        return Doc(self, doctype=doctype)


def pack(engine):
    """Construct the public boundary with a request-bound engine."""
    return TradingPack(engine)


def test_price_list_is_selling_only_and_native():
    e = Engine()
    assert pack(e).create_price_list('Wholesale AR', 'QAR') == 'new-record'
    assert e.saved == [dict(doctype='Price List', price_list_name='Wholesale AR',
                           currency='QAR', selling=1, buying=0, enabled=1)]


def test_item_price_keeps_explicit_decimal_and_uom():
    e = Engine()
    pack(e).create_item_price('Wholesale', 'demo-item', 'Unit', '12.50')
    assert e.saved[0]['price_list_rate'] == '12.50'
    assert e.saved[0]['uom'] == 'Unit'


def test_volume_discount_is_scoped_and_contains_no_expression():
    e = Engine()
    pack(e).create_volume_discount('Bulk', 'demo-company', 'Wholesale', 'demo-item', '10', '5')
    row = e.saved[0]
    assert (row['company'], row['for_price_list'], row['items']) == (
        'demo-company', 'Wholesale', [{'item_code': 'demo-item'}])
    assert row['discount_percentage'] == '5' and 'condition' not in row


def test_credit_upsert_preserves_other_company_and_disallows_zero_unlimited():
    e = Engine()
    pack(e).set_credit_limit('demo-customer', 'demo-company', '250')
    assert e.saved[0]['credit_limits'] == [
        {'company': 'other-company', 'credit_limit': '40', 'bypass_credit_limit_check': 0},
        {'company': 'demo-company', 'credit_limit': '250', 'bypass_credit_limit_check': 0}]


def test_credit_update_clears_bypass_without_replacing_other_rows():
    e = Engine()
    e.rows['Customer', 'demo-customer']['credit_limits'].append(
        dict(company='demo-company', credit_limit='10', bypass_credit_limit_check=1))
    pack(e).set_credit_limit('demo-customer', 'demo-company', '250')
    assert len(e.saved[0]['credit_limits']) == 2
    assert e.saved[0]['credit_limits'][1]['bypass_credit_limit_check'] == 0


def test_commission_uses_master_rate_and_native_draft_sales_team():
    e = Engine()
    p = pack(e)
    p.set_commission_rate('demo-rep', '2.5')
    p.set_sales_team('demo-order', [{'sales_person': 'demo-rep', 'allocated_percentage': '100'}])
    assert e.saved[0]['commission_rate'] == '2.5'
    assert e.saved[1]['sales_team'] == [dict(sales_person='demo-rep', allocated_percentage='100', commission_rate='3')]
    assert not {'incentives', 'allocated_amount', 'total_commission'} & e.saved[1].keys()


@pytest.mark.parametrize('method,args', [
    (TradingPack.create_price_list, ('Wholesale AR', 'QAR')),
    (TradingPack.create_item_price, ('Wholesale', 'demo-item', 'Unit', '12')),
    (TradingPack.create_volume_discount, ('Bulk', 'demo-company', 'Wholesale', 'demo-item', '10', '5')),
    (TradingPack.set_credit_limit, ('demo-customer', 'demo-company', '250')),
    (TradingPack.set_commission_rate, ('demo-rep', '3')),
    (TradingPack.set_sales_team, ('demo-order', [{'sales_person': 'demo-rep', 'allocated_percentage': '100'}])),
    (TradingPack.enforce_price_lists, ()),
])
def test_every_operation_fails_when_session_changes(method, args):
    e = Engine()
    p = pack(e)
    e.local.site = 'synthetic-b'
    with pytest.raises(TradingError, match='TRD-CONTEXT'):
        method(p, *args)
    assert not e.saved


@pytest.mark.parametrize('value', ['0', '-1', 'NaN', 'Infinity', True, 1.5, '1e3', ' 12 ', '9' * 25])
def test_invalid_credit_never_writes(value):
    e = Engine()
    with pytest.raises(TradingError, match='TRD-NUMBER'):
        pack(e).set_credit_limit('demo-customer', 'demo-company', value)
    assert not e.saved


@pytest.mark.parametrize('doctype,name,action', [
    ('Customer', 'demo-customer', 'write'), ('Company', 'demo-company', 'read'),
])
def test_credit_respects_document_and_company_permissions(doctype, name, action):
    e = Engine()
    e.denied.add((doctype, name, action))
    with pytest.raises(PermissionError):
        pack(e).set_credit_limit('demo-customer', 'demo-company', '250')
    assert not e.saved


def test_cannot_write_submitted_sales_order():
    e = Engine()
    e.rows['Sales Order', 'demo-order']['docstatus'] = 1
    with pytest.raises(TradingError, match='TRD-DRAFT'):
        pack(e).set_sales_team('demo-order', [{'sales_person': 'demo-rep', 'allocated_percentage': '100'}])
    assert not e.saved


@pytest.mark.parametrize('team', [[], [{'sales_person': 'demo-rep', 'allocated_percentage': '99'}],
    [{'sales_person': 'demo-rep', 'allocated_percentage': '50'}] * 2,
    [{'sales_person': 'demo-rep', 'allocated_percentage': '100', 'incentives': '500'}]])
def test_invalid_team_and_caller_calculated_incentives_are_rejected(team):
    e = Engine()
    with pytest.raises(TradingError):
        pack(e).set_sales_team('demo-order', team)
    assert not e.saved


def test_price_lists_must_be_enforced_before_prices_are_created():
    e = Engine()
    e.rows['Selling Settings', 'Selling Settings']['editable_price_list_rate'] = 1
    with pytest.raises(TradingError, match='TRD-PRICE'):
        pack(e).create_item_price('Wholesale', 'demo-item', 'Unit', '12')
    assert not e.saved


@pytest.mark.parametrize('user', ['', 'Guest'])
def test_anonymous_context_is_refused(user):
    e = Engine()
    e.session.user = user
    with pytest.raises(TradingError, match='TRD-CONTEXT'):
        pack(e)


def test_same_site_different_actor_is_refused():
    e = Engine()
    p = pack(e)
    e.session.user = 'other-user'
    with pytest.raises(TradingError, match='TRD-CONTEXT'):
        p.set_commission_rate('demo-rep', '5')
    assert not e.saved


@pytest.mark.parametrize('dt,name,action', [
    ('Price List', 'new-record', 'create'), ('Currency', 'QAR', 'read'),
    ('Selling Settings', 'Selling Settings', 'write'),
])
def test_price_list_creation_cannot_bypass_permissions(dt, name, action):
    e = Engine()
    e.denied.add((dt, name, action))
    with pytest.raises(PermissionError):
        pack(e).create_price_list('Wholesale AR', 'QAR')
    assert not e.saved


def test_missing_link_propagates_and_never_writes():
    e = Engine()
    with pytest.raises(KeyError):
        pack(e).create_item_price('Wholesale', 'missing-item', 'Unit', '12')
    assert not e.saved


def test_company_currency_mismatch_is_refused():
    e = Engine()
    e.rows['Company', 'demo-company']['default_currency'] = 'USD'
    with pytest.raises(TradingError, match='TRD-CURRENCY'):
        pack(e).create_volume_discount('Bulk', 'demo-company', 'Wholesale', 'demo-item', '10', '5')
    assert not e.saved


@pytest.mark.parametrize('field,value', [('enabled', 0), ('is_group', 1), ('commission_rate', '101')])
def test_ineligible_rep_and_invalid_master_rate_are_refused(field, value):
    e = Engine()
    e.rows['Sales Person', 'demo-rep'][field] = value
    with pytest.raises(TradingError):
        pack(e).set_sales_team('demo-order', [{'sales_person': 'demo-rep', 'allocated_percentage': '100'}])
    assert not e.saved


def test_duplicate_company_credit_rows_fail_closed():
    e = Engine()
    e.rows['Customer', 'demo-customer']['credit_limits'] = [dict(company='demo-company')] * 2
    with pytest.raises(TradingError, match='TRD-CREDIT'):
        pack(e).set_credit_limit('demo-customer', 'demo-company', '10')
    assert not e.saved


@pytest.mark.parametrize('name', ['', ' padded ', 'x\n', 'x' * 141])
def test_invalid_record_names_are_refused(name):
    e = Engine()
    with pytest.raises(TradingError, match='TRD-TEXT'):
        pack(e).create_price_list(name, 'QAR')
    assert not e.saved


def test_enforcing_price_lists_preserves_other_settings():
    e = Engine()
    e.rows['Selling Settings', 'Selling Settings'].update(editable_price_list_rate=1, unrelated='keep')
    pack(e).enforce_price_lists()
    assert e.saved[0]['editable_price_list_rate'] == 0 and e.saved[0]['unrelated'] == 'keep'


def test_arabic_names_are_preserved_as_data():
    e = Engine()
    pack(e).create_price_list('أسعار الجملة', 'QAR')
    assert e.saved[0]['price_list_name'] == 'أسعار الجملة'


@pytest.mark.parametrize('action', ['read', 'write'])
def test_hidden_credit_table_is_refused_without_returning_amounts(action):
    e = Engine()
    e.denied.add(('Customer', 'demo-customer', action + ':credit_limits'))
    with pytest.raises(TradingError, match='^TRD-FIELD$'):
        pack(e).set_credit_limit('demo-customer', 'demo-company', '250')
    assert not e.saved


@pytest.mark.parametrize('field', ['credit_limit', 'bypass_credit_limit_check'])
@pytest.mark.parametrize('action', ['read', 'write'])
def test_hidden_credit_child_fields_are_refused(field, action):
    e = Engine()
    e.denied.add(('Customer', 'demo-customer', action + ':' + field))
    with pytest.raises(TradingError, match='^TRD-FIELD$'):
        pack(e).set_credit_limit('demo-customer', 'demo-company', '250')
    assert not e.saved
