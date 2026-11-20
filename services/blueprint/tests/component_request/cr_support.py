import copy
import hashlib
import sys
from pathlib import Path

BP = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BP))

from component_request import Actor, ComponentRequests  # noqa: E402

T0 = "2026-11-20T10:00:00Z"
T1 = "2026-11-20T10:05:00Z"
T2 = "2026-11-20T10:10:00Z"
T3 = "2026-11-20T10:15:00Z"


TEN = "tenant-aaa1"
TEN2 = "tenant-bbb2"
KEY = hashlib.sha256(b"entity:visit_checklist").hexdigest()[:16]
RID = "CR-" + KEY


def gap(ref="visit_checklist", kind="entity", key=None, hint="configurable", rid=None, evidence=None):
    rid = rid or f"{kind}:{ref}"
    key = key or hashlib.sha256(rid.encode("utf-8")).hexdigest()[:16]
    return {"request_key": key, "requirement_id": rid, "kind": kind, "ref": ref, "kind_hint": hint,
            "reason_codes": ["no_provider"],
            "evidence": evidence if evidence is not None else [{"kind": "blueprint", "id": "/entities/13"}, {"kind": "provenance", "id": "interview:turn-013"}]}


def good_draft():
    return {
        "manifest": {
            "id": "sales.visit_checklist", "version": "0.1.0", "kind": "configurable",
            "name": {"ar": "قائمة فحص الزيارة", "en": "Visit checklist"},
            "description": "Visit checklist document linked to a sales invoice, with a reason and a status.",
            "provides": [{"capability": "sales.visit_checklist.manage", "artifacts": [
                {"type": "entity", "ref": "visit_checklist", "riskClass": "plain"}, {"type": "screen", "ref": "screens/visit_checklist"}]}],
            "requires": [], "parameters": [],
            "tests": [{"id": "unit_core", "kind": "unit", "path": "tests/test_core.py", "blocking": True},
                      {"id": "arabic_labels", "kind": "arabic_text", "path": "tests/test_arabic.py", "blocking": True}],
            "engineCompatibility": {"adapter": "change_engine", "engineRange": ">=0.1.0 <1.0.0"},
            "i18n": {"locales": ["ar", "en"], "rtlVerified": False},
            "dataHandling": {"storesPersonalData": False, "sendsDataToModels": False, "promotableToLibrary": False}},
        "spec": {
            "capabilities": [{"id": "sales.visit_checklist.manage", "summary": "Create and edit visit checklists linked to a customer"}],
            "fields": [{"entity": "visit_checklist", "name": "result", "type": "text", "required": True},
                       {"entity": "visit_checklist", "name": "customer", "type": "link", "required": True, "target": "customer"}],
            "permissions": [{"role": "sales_clerk", "action": "create"}, {"role": "sales_manager", "action": "read"}],
            "i18n_keys": ["sales.visit_checklist.title", "sales.visit_checklist.reason"],
            "test_plan": [{"id": "unit_core", "kind": "unit", "covers": ["sales.visit_checklist.manage"], "blocking": True},
                          {"id": "arabic_labels", "kind": "arabic_text", "covers": ["sales.visit_checklist.manage"], "blocking": True}]},
        "generalisation": {"rationale": "Any field sales team records checklists during customer visits, so one component serves all.",
                           "tenant_specific": False}}


class FakeDrafter:
    def __init__(self, result=None, exc=None):
        self.result, self.exc, self.briefs = result if result is not None else good_draft(), exc, []

    def draft(self, brief):
        self.briefs.append(brief)
        if self.exc:
            raise self.exc
        return copy.deepcopy(self.result)


class FakeLibrary:
    def __init__(self, manifests=()):
        self.m = {x["id"]: {x["version"]: x} for x in manifests}

    def list_components(self): return sorted(self.m)
    def versions(self, cid): return sorted(self.m.get(cid, {}))
    def get(self, cid, v): return self.m.get(cid, {}).get(v)


from dataclasses import dataclass  # noqa: E402


import component_request.policy  # noqa: E402,F401  (puts the operate and events paths on sys.path)
from agui.ports import Principal as Prin  # noqa: E402  (the real verified-caller type)


def ask(s, g, now, tenant=TEN, subject="discovery-agent", session=None):
    return s.intake(g, Prin(tenant, subject, (), session or "sess-" + tenant), now)


def forge(s, rid, fn, reseal=False):
    """Simulate a store writer; with reseal=True, one who also holds the integrity key."""
    fn(s._records[rid])
    if reseal:
        s._seal(s._records[rid])


AGENT = Actor("agent", "discovery-agent")
CLERK = Actor("human", "founder-a", ("component_reviewer",), True)
REVIEWER = Actor("human", "founder-b", ("component_reviewer",), True)


def build(result=None, exc=None, library=(), **kw):
    d = FakeDrafter(result, exc)
    kw.setdefault("min_tenants", 1)
    kw.setdefault("integrity_key", b"test-integrity-key")
    kw.setdefault("host_now", lambda: "2026-11-20T12:30:00Z")
    return ComponentRequests(d, FakeLibrary(library), owner_github="example-owner", **kw), d
