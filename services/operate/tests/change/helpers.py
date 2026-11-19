import copy
import json
from pathlib import Path

from agui.ports import Principal
from change import ChangeService
from change.models import DraftRequest
from router import IntentRouter, RouteContext
from router.models import RouteDecision

FIXTURE = Path(__file__).resolve().parents[4] / "services/blueprint/fixtures/trading-distribution.blueprint.json"
TENANT, USER, SESSION = "t1", "u1", "s1"
OWNER = Principal(TENANT, USER, ("owner",), SESSION)


def blueprint():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class FakeBlueprints:
    """Stands for the existing Blueprint path. Records submitted diffs; never touches an engine."""
    def __init__(self, bp=None, fail=False):
        self.bp, self.fail, self.submitted = bp or blueprint(), fail, []

    def current(self, tenant_id):
        return copy.deepcopy(self.bp)

    def validation_context(self, tenant_id):
        return None

    def submit_change(self, tenant_id, diff, proposal_digest, idempotency_key):
        if self.fail:
            raise RuntimeError("engine down")
        self.submitted.append((tenant_id, diff, proposal_digest))
        return {"ok": True}


class ScriptedDrafter:
    def __init__(self, out):
        self.out, self.requests = out, []

    def draft(self, request: DraftRequest):
        self.requests.append(request)
        if isinstance(self.out, Exception):
            raise self.out
        return self.out


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


LABEL = [{"op": "set", "path": ["entities", "customer", "fields", "phone", "labels", "en"], "value": "Mobile number"}]
ADD_FIELD = [{"op": "add", "path": ["entities", "customer", "fields"],
              "value": {"id": "whatsapp", "type": "string", "labels": {"ar": "واتساب", "en": "WhatsApp"},
                        "maxLength": 20}}]


def change_decision(text="change the label of the phone field on customer", risk="R2"):
    return RouteDecision("change", "high", ("needs_confirmation",), requires_confirmation=True, risk_hint=risk)


def confirm_decision(router_text, preview, clock):
    """Run the real router with the host-set Pending: a yes becomes a confirming decision."""
    ctx = RouteContext(pending=ChangePending.of(preview), now=clock())
    return IntentRouter().route(router_text, ctx)


class ChangePending:
    @staticmethod
    def of(preview):
        from router.models import Pending
        return Pending("change", preview.action_id, preview.digest, preview.risk, preview.expires_at)


def make(out=LABEL, bp=None, clock=None, **kw):
    clock = clock or Clock()
    blueprints = FakeBlueprints(bp, kw.pop("fail", False))
    drafter = ScriptedDrafter(out)
    audit = []
    svc = ChangeService(blueprints=blueprints, drafter=drafter, clock=clock, allowed_roles={"owner"},
                        audit=audit.append, **kw)
    return svc, blueprints, drafter, clock, audit
