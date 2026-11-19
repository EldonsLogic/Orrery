import pytest

from router import IntentRouter, Pending, RouteContext
from router.models import MODES, REASONS

R = IntentRouter()
LIVE = RouteContext(entity_names=("Shipment", "شحنة"))
PRE = RouteContext(blueprint_live=False)


@pytest.mark.parametrize("text,mode", [
    ("Show me the VAT summary for last quarter", "ask"),
    ("What is the stock on hand for item CARTON-12?", "ask"),
    ("How do I create a credit note?", "ask"),
    ("should I cancel invoice 12", "ask"),
    ("Which shipments are late", "ask"),
    ("اعرض ملخص ضريبة القيمة المضافة للربع الأخير", "ask"),
    ("وش المستحقات اللي علينا للموردين هالشهر؟", "ask"),
    ("كيف أنشئ فاتورة؟", "ask"),
    ("Show لي الـ VAT summary للربع الأخير", "ask"),
    ("نحتاج trial balance للأكتوبر", "ask"),
    ("Create a sales invoice for Al Noor Trading: 10 cartons", "act"),
    ("Cancel invoice INV-0412", "act"),
    ("I want to create a purchase order for 500 bottles", "act"),
    ("Please post a receipt voucher for 5,000 SAR", "act"),
    ("أنشئ فاتورة مبيعات للعميل مؤسسة النيل", "act"),
    ("ابغى أعمل PO لدلتا Packaging، 500 bottles", "act"),
    ("سجل payment voucher بـ ٣٠٠٠ SAR للكهربا", "act"),
    ("Approve الدفعة AP-17 لو سمحت", "act"),
    ("Add a custom field to customers called region", "change"),
    ("Change the approval limit for purchase orders to 5000", "change"),
    ("Enable the workflow for sales orders", "change"),
    ("أضف حقل جديد للعملاء", "change"),
    ("غير صلاحيات دور المحاسب", "change"),
    ("We are a trading company with 40 employees", "discover"),
    ("شركتنا تبيع قطع غيار", "discover"),
    ("set up my business", "discover"),
])
def test_modes(text, mode):
    d = R.route(text, LIVE)
    assert d.mode == mode and not d.abstain, d
    assert d.requires_confirmation == (mode in ("act", "change"))
    assert set(d.reasons) <= REASONS and d.mode in MODES


def test_entity_names_from_blueprint_make_an_object():
    assert R.route("Create a shipment for Delta", LIVE).confidence == "high"
    assert "entity_match" in R.route("Cancel shipment 7", LIVE).reasons
    assert R.route("Cancel it", LIVE).abstain  # medium rules, no corroboration: ask


@pytest.mark.parametrize("text", [
    "Can you record the money from the shop yesterday?", "ممكن تسجل سند قبض", "Create invoice and show the report",
    "show the stock and then delete customer Nile", "Give Ahmed a custody advance of 2,000 SAR", "hmm", "",
    "Add a field and create an invoice for Nile Supplies", "yes",
])
def test_uncertainty_resolves_to_ask_with_a_question(text):
    d = R.route(text, LIVE)
    assert d.mode == "ask" and d.abstain and d.clarify_key and not d.requires_confirmation and d.confidence == "low"


def test_slash_commands_only_at_the_start():
    assert R.route("/change", LIVE).mode == "change" and R.route("/نفذ", LIVE).mode == "act"
    assert R.route("/change", LIVE).explicit_command
    d = R.route("show the report /change", LIVE)
    assert d.mode == "ask" and not d.explicit_command


def test_before_go_live():
    assert R.route("Create a sales invoice for Nile", PRE).abstain
    assert "act_unavailable" in R.route("Create a sales invoice for Nile", PRE).reasons
    d = R.route("Add a custom field to customers", PRE)
    assert d.mode == "discover" and "pre_live_change_is_discovery" in d.reasons
    assert R.route("We mostly sell to restaurants", PRE).mode == "discover"
    assert R.route("/act", PRE).abstain


PA = Pending("act", "a1", "h1", "R1", 1000.0)


def test_confirmation_only_against_a_host_pending():
    ctx = RouteContext(pending=PA, now=10.0)
    d = R.route("yes", ctx)
    assert d.mode == "act" and d.extra["confirms_pending"] and not d.requires_confirmation
    assert R.route("نعم", RouteContext(pending=Pending("change", "a1", "h1", "R2", 1000.0), now=10.0)).mode == "change"
    assert R.route("no", ctx).mode == "ask"
    assert R.route("yes", LIVE).abstain
    # a pending of a non-privileged mode, or text that only contains "yes", does not confirm
    assert R.route("yes", RouteContext(pending=Pending("ask"))).abstain
    assert R.route("yes create invoice for Nile", ctx).mode == "ask"  # only the bare reply confirms


def test_arabic_indic_digits_and_code_switching():
    a = R.route("أنشئ فاتورة لـ ١٢٣ كرتون", LIVE)
    b = R.route("أنشئ فاتورة لـ 123 كرتون", LIVE)
    assert (a.mode, a.reasons, a.risk_hint) == (b.mode, b.reasons, b.risk_hint) == ("act", b.reasons, "R3")
    assert R.route("اعمل Credit note لـ INV-0399", LIVE).risk_hint == "R3"
    assert R.route("Cancel الفاتورة ٠٤١٢", LIVE).risk_hint == "R4"


def test_risk_floor_and_hint_never_lower():
    assert R.route("Make a quotation for Nile", LIVE).risk_hint == "R1"
    assert R.route("Make a quotation for Nile", LIVE, risk_hint="R3").risk_hint == "R3"
    assert "hint_raised_risk" in R.route("Make a quotation for Nile", LIVE, risk_hint="R3").reasons
    assert R.route("Create a sales invoice for Nile", LIVE, risk_hint="R0").risk_hint == "R3"
    assert R.route("Show the report", LIVE, risk_hint="R2").risk_hint == "R2"
    d = R.route("Show the report", LIVE, risk_hint="R9")
    assert d.risk_hint == "R4" and "hint_invalid" in d.reasons  # unreadable hint fails closed
    assert R.route("Change the approval limit to 5000", LIVE).risk_hint == "R3"
    assert R.route("Add a custom field to customers", LIVE).risk_hint == "R2"
