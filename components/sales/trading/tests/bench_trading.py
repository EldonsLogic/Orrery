"""Rollback-only integration proof for a synthetic pinned bench.

The trusted bench runner calls run(engine) within a connected request. This never
commits; it restores the previous user and rolls back fixture writes on every exit.
"""
from trading import TradingPack


def run(engine):
    """Exercise native hooks and a real permission denial; return completed proof names."""
    original_user = engine.session.user
    proofs = []
    engine.db.savepoint('erp011')
    try:
        engine.set_user('Administrator')  # Fixture setup only, never part of the component.
        if not engine.db.exists('Warehouse Type', 'Transit'):
            engine.get_doc(dict(doctype='Warehouse Type', name='Transit')).insert()
        for dt, name, field in [
            ('Customer Group', 'All Customer Groups', 'customer_group_name'),
            ('Territory', 'All Territories', 'territory_name'),
            ('Item Group', 'All Item Groups', 'item_group_name'),
            ('Sales Person', 'All Sales Persons', 'sales_person_name'),
        ]:
            if not engine.db.exists(dt, name):
                engine.get_doc(dict(doctype=dt, is_group=1, **{field: name})).insert()
        engine.get_doc(dict(doctype='Customer Group', customer_group_name='ERP011 Synthetic Group',
                            parent_customer_group='All Customer Groups', is_group=0)).insert()
        if not engine.db.exists('UOM', 'Nos'):
            engine.get_doc(dict(doctype='UOM', uom_name='Nos', must_be_whole_number=1)).insert()
        company_doc = engine.get_doc(dict(doctype='Company', company_name='ERP011 Synthetic Co',
                                          abbr='E11', country='Qatar', default_currency='QAR',
                                          chart_of_accounts='Standard')).insert()
        company, currency = company_doc.name, company_doc.default_currency
        before = engine.db.count('GL Entry')
        customer = engine.get_doc(dict(doctype='Customer', customer_name='ERP011 Synthetic Customer',
                                      customer_type='Company', customer_group='ERP011 Synthetic Group',
                                      territory='All Territories')).insert()
        item = engine.get_doc(dict(doctype='Item', item_code='ERP011-SYNTHETIC-ITEM',
                                  item_group='All Item Groups', stock_uom='Nos', is_stock_item=0)).insert()
        rep = engine.get_doc(dict(doctype='Sales Person', sales_person_name='ERP011 Synthetic Rep',
                                 enabled=1, is_group=0)).insert()
        p = TradingPack(engine)
        p.enforce_price_lists()
        price_list = p.create_price_list('ERP011 Synthetic Wholesale', currency)
        price = p.create_item_price(price_list, item.name, 'Nos', '12.50')
        assert engine.get_doc('Item Price', price).price_list_rate == 12.5
        proofs.append('native price list and item price')
        rule = p.create_volume_discount('ERP011 Synthetic Bulk', company, price_list, item.name, '10', '5')
        assert engine.get_doc('Pricing Rule', rule).condition in ('', None)
        proofs.append('native scoped volume discount')
        p.set_credit_limit(customer.name, company, '250')
        p.set_credit_limit(customer.name, company, '300')
        limits = engine.get_doc('Customer', customer.name).credit_limits
        assert len(limits) == 1 and limits[0].credit_limit == 300
        assert limits[0].bypass_credit_limit_check == 0
        proofs.append('native credit upsert without bypass')
        p.set_commission_rate(rep.name, '2.5')
        order = engine.get_doc(dict(
            doctype='Sales Order', company=company, customer=customer.name,
            transaction_date='2026-11-19', delivery_date='2026-11-20',
            selling_price_list=price_list, currency=currency,
            items=[dict(item_code=item.name, qty=1, rate=12.5, delivery_date='2026-11-20')])).insert()
        p.set_sales_team(order.name, [dict(sales_person=rep.name, allocated_percentage='100')])
        saved = engine.get_doc('Sales Order', order.name)
        assert saved.docstatus == 0 and len(saved.sales_team) == 1
        assert str(saved.sales_team[0].commission_rate) == '2.5'
        assert engine.db.count('GL Entry') == before
        proofs.append('native commission attribution with no GL posting')
        user = engine.get_doc(dict(doctype='User', email='erp011@example.invalid',
                                   first_name='ERP011 Synthetic', send_welcome_email=0)).insert()
        engine.set_user(user.name)
        denied = False
        try:
            TradingPack(engine).set_commission_rate(rep.name, '90')
        except engine.PermissionError:
            denied = True
        assert denied, 'An authenticated user without master write permission must be denied'
        proofs.append('real engine permission denial')
        return proofs
    finally:
        engine.set_user(original_user)
        engine.db.rollback(save_point='erp011')
