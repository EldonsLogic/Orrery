import pytest

from metrics import MetricError, MetricService, Principal, default_registry

T = "t_abc"
OWNER = Principal(tenant_id=T, user_id="u1", role_ids=frozenset({"owner"}))
CLERK = Principal(tenant_id=T, user_id="u2", role_ids=frozenset({"warehouse"}))


def ev(seq, typ, when, **data):
    return {"event_id": f"E{seq:04d}", "type": typ, "tenant_id": T, "sequence": seq,
            "occurred_at": when, "data": data}


def inv(seq, when, total, doc="invoice", cur="SAR"):
    return ev(seq, "document.issued", when, document_id=f"INV-{seq}", document_type=doc,
              total=total, currency=cur, einvoice_status="cleared")


def pay(seq, when, invoice, amount, cur="SAR"):
    return ev(seq, "payment.created", when, invoice_id=invoice, amount=amount, currency=cur)


EVENTS = [
    inv(1, "2026-10-30T10:00:00Z", "100.00"),
    inv(2, "2026-11-02T10:00:00Z", "115.005"),
    inv(3, "2026-11-10T10:00:00Z", "50.00"),
    inv(4, "2026-11-11T10:00:00Z", "10.00", doc="credit_note"),
    pay(5, "2026-11-12T10:00:00Z", "INV-1", "100.00"),
    inv(6, "2026-12-01T00:00:00Z", "999.00"),
]


def svc(events=EVENTS):
    return MetricService(default_registry(), lambda tenant: list(events))


def test_sales_revenue_month_half_up_and_credit_note():
    r = svc().get(OWNER, "sales.revenue", {"period": "2026-11", "currency": "SAR"})
    assert r["value"] == "155.01"  # 115.005 + 50 - 10 = 155.005, half-up
    assert r["currency"] == "SAR" and r["unit"] == "money"


def test_invoice_count_excludes_credit_notes_and_other_months():
    r = svc().get(OWNER, "sales.order_count", {"period": "2026-11"})
    assert r["value"] == 2 and r["unit"] == "count"


def test_receivables_as_of():
    r = svc().get(OWNER, "finance.receivables_outstanding", {"as_of": "2026-11-30", "currency": "SAR"})
    assert r["value"] == "155.01"  # 100+115.005+50-10-100
    r = svc().get(OWNER, "finance.receivables_outstanding", {"as_of": "2026-11-11", "currency": "SAR"})
    assert r["value"] == "255.01"  # payment not yet made


def test_permission_checked_from_caller_roles():
    with pytest.raises(MetricError) as e:
        svc().get(CLERK, "sales.revenue", {"period": "2026-11", "currency": "SAR"})
    assert e.value.code == "MET-002"


def test_unknown_metric_and_bad_params():
    for mid, params, code in [
        ("nope.x", {}, "MET-001"),
        ("sales.revenue", {"period": "2026-13", "currency": "SAR"}, "MET-003"),
        ("sales.revenue", {"period": "2026-11"}, "MET-003"),
        ("sales.revenue", {"period": "2026-11", "currency": "USD"}, "MET-003"),
        ("sales.revenue", {"period": "2026-11", "currency": "SAR", "x": 1}, "MET-003"),
        ("finance.receivables_outstanding", {"as_of": "2026-11-3", "currency": "SAR"}, "MET-003"),
    ]:
        with pytest.raises(MetricError) as e:
            svc().get(OWNER, mid, params)
        assert e.value.code == code


def test_foreign_tenant_event_refused():
    bad = dict(EVENTS[1], tenant_id="t_other")
    with pytest.raises(MetricError) as e:
        svc([bad]).get(OWNER, "sales.order_count", {"period": "2026-11"})
    assert e.value.code == "MET-004"


def test_mixed_currency_and_bad_amount_refused():
    with pytest.raises(MetricError) as e:
        svc([inv(1, "2026-11-02T10:00:00Z", "5.00", cur="AED")]).get(
            OWNER, "sales.revenue", {"period": "2026-11", "currency": "SAR"})
    assert e.value.code == "MET-005"
    with pytest.raises(MetricError) as e:
        svc([inv(1, "2026-11-02T10:00:00Z", "1e3")]).get(
            OWNER, "sales.revenue", {"period": "2026-11", "currency": "SAR"})
    assert e.value.code == "MET-006"


def test_duplicate_event_ids_counted_once():
    r = svc(EVENTS + [EVENTS[1]]).get(OWNER, "sales.order_count", {"period": "2026-11"})
    assert r["value"] == 2


def test_missing_principal_fails_closed():
    with pytest.raises(MetricError) as e:
        svc().get(None, "sales.order_count", {"period": "2026-11"})
    assert e.value.code == "MET-007"


def test_cache_invalidated_by_new_events_and_permission_rechecked():
    store = {"events": list(EVENTS)}
    s = MetricService(default_registry(), lambda tenant: list(store["events"]))
    p = {"period": "2026-11"}
    assert s.get(OWNER, "sales.order_count", p)["cached"] is False
    assert s.get(OWNER, "sales.order_count", p)["cached"] is True
    store["events"].append(inv(7, "2026-11-20T10:00:00Z", "1.00"))
    r = s.get(OWNER, "sales.order_count", p)
    assert r["value"] == 3 and r["cached"] is False
    with pytest.raises(MetricError):
        s.get(CLERK, "sales.order_count", p)


def test_cache_does_not_cross_tenants():
    s = MetricService(default_registry(), lambda t: [dict(e, tenant_id=t) for e in EVENTS])
    other = Principal(tenant_id="t_two", user_id="u9", role_ids=frozenset({"owner"}))
    s.get(OWNER, "sales.order_count", {"period": "2026-11"})
    assert s.get(other, "sales.order_count", {"period": "2026-11"})["cached"] is False


def test_catalog_lists_only_permitted():
    assert svc().catalog(CLERK) == []
    assert len(svc().catalog(OWNER)) == 3
