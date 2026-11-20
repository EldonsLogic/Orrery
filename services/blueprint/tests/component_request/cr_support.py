import copy
import sys
from pathlib import Path

BP = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BP))

from component_request import Actor, ComponentRequests  # noqa: E402

T0 = "2026-11-20T10:00:00Z"
T1 = "2026-11-20T10:05:00Z"
T2 = "2026-11-20T10:10:00Z"
T3 = "2026-11-20T10:15:00Z"


def gap(ref="credit_note", kind="entity", key="07141fae2b676cce", hint="configurable", rid=None, evidence=None):
    return {"request_key": key, "requirement_id": rid or f"{kind}:{ref}", "kind": kind, "ref": ref, "kind_hint": hint,
            "reason_codes": ["no_provider"],
            "evidence": evidence if evidence is not None else [{"kind": "blueprint", "id": "/entities/13"}, {"kind": "provenance", "id": "interview:turn-013"}]}


def good_draft():
    return {
        "manifest": {
            "id": "sales.credit_note", "version": "0.1.0", "kind": "configurable",
            "name": {"ar": "إشعار دائن", "en": "Credit note"},
            "description": "Credit note document linked to a sales invoice, with a reason and a status.",
            "provides": [{"capability": "sales.credit_note.manage", "artifacts": [
                {"type": "entity", "ref": "credit_note", "riskClass": "plain"}, {"type": "screen", "ref": "screens/credit_note"}]}],
            "requires": [], "parameters": [],
            "tests": [{"id": "unit_core", "kind": "unit", "path": "tests/test_core.py", "blocking": True},
                      {"id": "arabic_labels", "kind": "arabic_text", "path": "tests/test_arabic.py", "blocking": True}],
            "engineCompatibility": {"adapter": "change_engine", "engineRange": ">=0.1.0 <1.0.0"},
            "i18n": {"locales": ["ar", "en"], "rtlVerified": False},
            "dataHandling": {"storesPersonalData": False, "sendsDataToModels": False, "promotableToLibrary": False}},
        "spec": {
            "capabilities": [{"id": "sales.credit_note.manage", "summary": "Create and edit credit notes linked to an invoice"}],
            "fields": [{"entity": "credit_note", "name": "reason", "type": "text", "required": True},
                       {"entity": "credit_note", "name": "invoice", "type": "link", "required": True}],
            "permissions": [{"role": "sales_clerk", "action": "create"}, {"role": "sales_manager", "action": "read"}],
            "i18n_keys": ["sales.credit_note.title", "sales.credit_note.reason"],
            "test_plan": [{"id": "unit_core", "kind": "unit", "covers": ["sales.credit_note.manage"], "blocking": True},
                          {"id": "arabic_labels", "kind": "arabic_text", "covers": ["sales.credit_note.manage"], "blocking": True}]},
        "generalisation": {"rationale": "Any trading company issues credit notes against invoices, so one component serves all.",
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


AGENT = Actor("agent", "discovery-agent")
CLERK = Actor("human", "founder-a", ("component_reviewer",), True)
REVIEWER = Actor("human", "founder-b", ("component_reviewer",), True)


def build(result=None, exc=None, library=()):
    d = FakeDrafter(result, exc)
    return ComponentRequests(d, FakeLibrary(library), owner_github="example-owner"), d
