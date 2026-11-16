"""Builders for the conformance suite: contexts, sealed artifacts, an initial-build artifact, call helpers.

Nothing here imports adapter internals except the canonical-hash helper, which the contract fixes (sections 5.8, 9.1).
The initial build is a stand-in for the compiler (BPL-004, not built): one step per Blueprint element.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from .fake import artifact_hashes, canon, sha

ROOT = Path(__file__).resolve().parents[3]
EXAMPLES = ROOT / "contracts" / "examples"
BLUEPRINT_ID = "example-trading-001"
ENGINE_TARGET = {"adapter": "frappe", "versionSet": "set-example"}
USER = {"kind": "user", "id": "u_owner1", "roleIds": ["owner"]}
_counter = {"n": 0}
_ULID = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def ulid() -> str:
    _counter["n"] += 1
    n, out = _counter["n"], ""
    for _ in range(26):
        out, n = _ULID[n % 32] + out, n // 32
    return out


def ctx(tenant="t_alpha", service="control_plane", who=USER, version="0.1.2", **extra) -> dict:
    caller = {"service": service, "onBehalfOf": copy.deepcopy(who)}
    return {"contractVersion": version, "requestId": ulid(), "correlationId": "corr-" + tenant, "tenantId": tenant,
            "caller": caller, "deadlineMs": 60000, **extra}


def key() -> str:
    return "idem_" + ulid()


def seal(artifact: dict) -> dict:
    """Recompute the embedded inverse's and the artifact's own hash and id after an edit."""
    if artifact.get("inverse"):
        seal(artifact["inverse"])
    digest, art_id = artifact_hashes(artifact)
    artifact["integrity"]["contentHash"], artifact["artifactId"] = digest, art_id
    return artifact


def sample(name: str) -> dict:
    return json.loads((EXAMPLES / f"compiled-artifact-{name}.json").read_text(encoding="utf-8"))


def blueprint() -> dict:
    return json.loads((EXAMPLES / "blueprint-trading-minimal.json").read_text(encoding="utf-8"))


_PHASE = {"settings.set": 1, "component.enable": 2, "component.configure": 2, "location.upsert": 3, "entity.add": 4,
          "field.add": 5, "relation.add": 5, "option.add": 5, "binding.add": 5, "entity.set_property": 6,
          "field.set_property": 6, "relation.set_property": 6, "binding.set_property": 6, "field.reorder": 6,
          "option.reorder": 6, "role.upsert": 7, "workflow.upsert": 8, "approval.upsert": 9, "report.upsert": 10,
          "report.disable": 11, "approval.disable": 12, "workflow.disable": 13, "role.disable": 14,
          "binding.disable": 15, "option.quarantine": 15, "relation.quarantine": 15, "field.quarantine": 15,
          "entity.quarantine": 16, "location.disable": 17, "component.disable": 18}
# Entities the fake treats as protected (ledger, identity). The real adapter's owner adds their own list (open question 6).
PROTECTED = ["general_ledger", "user_account"]
_KIND = {"components": ("component.enable", "component"), "locations": ("location.upsert", "location"),
         "entities": ("entity.add", "entity"), "roles": ("role.upsert", "role"), "workflows": ("workflow.upsert", "workflow"),
         "approvals": ("approval.upsert", "approval"), "reports": ("report.upsert", "report")}


def make_step(kind: str, pointer: str, subject_kind: str, subject_id, params: dict, ddl="none", impact="config", parents=()) -> dict:
    return {"seq": 0, "phase": _PHASE[kind], "kind": kind,
            "subject": {"kind": subject_kind, "id": subject_id, "parents": [{"kind": k, "id": i} for k, i in parents]},
            "pointer": pointer, "impact": impact, "ddlImpact": ddl, "reversible": True, "params": params, "sourceOps": [pointer]}


def initial_build(bp: dict | None = None) -> dict:
    """Initial-build artifact (base null) for the example Blueprint at revision 1, as the compiler would emit it."""
    bp = bp or blueprint()
    steps = []
    for name in ("company", "compliance", "i18n"):
        for prop, value in bp[name].items():
            steps.append(make_step("settings.set", f"/{name}", name, None, {"property": f"/{prop}", "after": value}))
    for section, (kind, subject) in _KIND.items():
        for node in bp[section]:
            ddl = "additive" if kind == "entity.add" else "none"
            steps.append(make_step(kind, f"/{section}/{node['id']}", subject, node["id"], {"definition": node}, ddl=ddl,
                                   impact="data_shape" if ddl == "additive" else "access" if kind == "role.upsert" else "config"))
    steps.sort(key=lambda s: (s["phase"], s["pointer"], s["kind"], s["params"].get("property", "")))
    for i, s in enumerate(steps, 1):
        s["seq"] = i
    pcs = [{"id": f"pc_{i:03d}", "check": "exists", "pointer": f"/entities/{e['id']}"} for i, e in enumerate(bp["entities"], 1)]
    pcs.append({"id": f"pc_{len(pcs) + 1:03d}", "check": "count_equals", "pointer": "/entities/customer/fields",
                "expected": len(bp["entities"][0]["fields"])})
    counts = {k: 0 for k in ("cosmetic", "config", "data_shape", "destructive", "compliance", "access", "branding")}
    art = {"artifactSchema": "0.1.0", "artifactId": "art_" + "0" * 32, "kind": "forward",
           "compiler": {"name": "bpl-compiler", "version": "0.1.0"},
           "blueprint": {"id": bp["meta"]["id"], "base": None, "diffHash": None,
                         "target": {"hash": sha(bp), "revision": bp["meta"]["revision"]}},
           "engineTarget": copy.deepcopy(ENGINE_TARGET),
           "components": [{"id": c["id"], "version": "0.1.0"} for c in sorted(bp["components"], key=lambda c: c["id"])],
           "steps": steps, "skippedOps": [], "postConditions": pcs,
           "risk": {"counts": counts, "total": 0, "maxImpact": "data_shape", "needsDdlPlanGate": True, "touchesCompliance": False,
                    "touchesAccess": True, "touchesLedgerOrTax": False, "requiresTeamReview": False, "irreversibleSteps": 0},
           "inverse": None, "integrity": {"algorithm": "sha256-canonical-json-v1", "contentHash": "sha256:" + "0" * 64, "signature": None}}
    return seal(art)


# ------------------------------------------------------------------ call helpers
def error_of(resp: dict) -> dict | None:
    """The error of a response: top-level (before acquire) or inside an outcome (after the operation record exists)."""
    if not resp["ok"]:
        return resp["error"]
    return resp["result"].get("error") if isinstance(resp["result"], dict) else None


def code_of(resp: dict) -> str | None:
    err = error_of(resp)
    return err["code"] if err else None


def rejected_error(resp: dict) -> dict:
    """The error of an apply or rollback refused in `inspect`: an outcome `rejected`, not an envelope (section 5.6.1)."""
    assert resp["ok"] and resp["result"]["status"] == "rejected", resp
    return resp["result"]["error"]


def provision(h, tenant="t_alpha", site_class="production", blueprint_id=BLUEPRINT_ID, target=None, k=None):
    return h.call("provision_site", ctx(tenant), {"idempotencyKey": k or key(), "engineTarget": copy.deepcopy(target or ENGINE_TARGET),
                                                   "countryPack": "sa", "siteClass": site_class, "blueprintId": blueprint_id})


def approvals_for(plan_result: dict, artifact: dict) -> dict:
    ap = {"changeApproved": ulid()}
    if plan_result["verdict"] == "needs_gate_approval":
        ap["gateApproved"] = ulid()
    if artifact["risk"]["requiresTeamReview"]:
        ap["teamReviewed"] = ulid()
    return ap


def plan(h, artifact, tenant="t_alpha", op="plan", **extra):
    return h.call(op, ctx(tenant), {"artifact": artifact, **extra})


def apply_artifact(h, artifact, tenant="t_alpha", k=None, approvals=None, token=None, who=USER):
    """plan then apply with the approvals the plan asks for; returns the apply response."""
    p = plan(h, artifact, tenant)
    assert p["ok"], p
    return h.call("apply", ctx(tenant, who=who), {
        "idempotencyKey": k or key(), "artifact": artifact, "planToken": token or p["result"]["planToken"],
        "approvals": approvals or approvals_for(p["result"], artifact)})


def rollback(h, forward, tenant="t_alpha", k=None, approvals=None, reason="owner_request", who=USER):
    return h.call("rollback", ctx(tenant, who=who), {
        "idempotencyKey": k or key(), "forwardArtifact": forward, "reason": reason,
        "approvals": approvals or {"rollbackApproved": ulid()}})


def export(h, tenant="t_alpha"):
    r = h.call("export_config", ctx(tenant), {})
    assert r["ok"], r
    return r["result"]


def status(h, tenant="t_alpha"):
    r = h.call("site_status", ctx(tenant), {})
    return r["result"] if r["ok"] else r["error"]


def snapshot(h, tenant="t_alpha") -> tuple:
    """What 'no effect' compares (section 14): export hash, retained, site status. Events are compared separately (8.2)."""
    e = export(h, tenant)
    return e["exportHash"], canon(e["retained"]), canon(status(h, tenant))


def site_at_rev1(h, tenant="t_alpha", site_class="production"):
    """A provisioned site with the example Blueprint built to revision 1 (initial build applied)."""
    assert provision(h, tenant, site_class)["ok"]
    build = initial_build()
    out = apply_artifact(h, build, tenant)
    assert out["ok"] and out["result"]["status"] == "applied", out
    return build


# ------------------------------------------------------------------ derived artifacts (stand-ins for the compiler)
def invert_step(step: dict) -> dict | None:
    """The inverse of one step as the compiler would emit it (None when this stand-in cannot invert the kind)."""
    kind, inv = step["kind"], copy.deepcopy(step)
    params = inv["params"]
    if kind.endswith(".add"):
        undo = next((kind[:-4] + ending for ending in (".quarantine", ".disable") if kind[:-4] + ending in _PHASE), None)
        if undo is None:
            return None
        inv.update(kind=undo, phase=_PHASE[undo], impact="destructive", ddlImpact="none")
    elif kind.endswith(".quarantine"):
        inv.update(kind=kind[:-11] + ".add", phase=_PHASE[kind[:-11] + ".add"], impact="data_shape", ddlImpact="additive")
    elif kind.endswith(".set_property"):
        params["before"], params["after"] = step["params"]["after"], step["params"]["before"]
    else:
        return None
    return inv


def with_inverse(art: dict) -> dict:
    """Give `art` the real inverse of its own steps (reverse order, renumbered), then seal it."""
    inverse = [invert_step(s) for s in art["steps"]]
    if None in inverse or not inverse:
        return seal(art)
    inverse = sorted(inverse, key=lambda s: (s["phase"], s["pointer"], s["kind"]))
    for i, s in enumerate(inverse, 1):
        s["seq"] = i
    art["inverse"]["steps"] = inverse
    art["inverse"]["postConditions"] = [{"id": f"pc_{i:03d}", "check": "quarantined" if s["kind"].endswith(".quarantine") else "disabled" if s["kind"].endswith(".disable") else "exists",
                                         "pointer": s["pointer"]} for i, s in enumerate(inverse, 1) if s["kind"].endswith((".quarantine", ".disable", ".add"))]
    return seal(art)


def variant(steps: list[dict], pcs: list[dict] | None = None, template: str = "add-field", **risk) -> dict:
    """A sealed forward artifact (base revision 1) with the given steps, built from a sample so the rest is valid."""
    art = sample(template)
    steps = sorted(copy.deepcopy(steps), key=lambda s: (s["phase"], s["pointer"], s["kind"]))
    for i, s in enumerate(steps, 1):
        s["seq"] = i
    art["steps"] = steps
    art["postConditions"] = pcs if pcs is not None else [
        {"id": f"pc_{i:03d}", "check": "exists", "pointer": s["pointer"]} for i, s in enumerate(steps, 1)
        if s["kind"].endswith((".add", ".upsert"))]
    art["risk"].update(risk)
    return with_inverse(art)


def field_step(entity: str, fid: str, kind="field.add", ftype="integer", **props) -> dict:
    definition = {"id": fid, "type": ftype, "labels": {"ar": "حقل", "en": fid}, **props}
    ddl = "additive" if kind == "field.add" else "none"
    return make_step(kind, f"/entities/{entity}/fields/{fid}", "field", fid, {"definition": definition}, ddl=ddl,
                     impact="data_shape" if ddl == "additive" else "destructive", parents=[("entity", entity)])


def prop_step(entity: str, fid: str, prop: str, before, after, ddl="semantic") -> dict:
    return make_step("field.set_property", f"/entities/{entity}/fields/{fid}", "field", fid,
                     {"property": prop, "before": before, "after": after}, ddl=ddl, impact="data_shape", parents=[("entity", entity)])


def entity_step(eid: str) -> dict:
    node = {"id": eid, "labels": {"ar": "كيان", "en": eid}, "kind": "master", "fields": []}
    return make_step("entity.add", f"/entities/{eid}", "entity", eid, {"definition": node}, ddl="additive", impact="data_shape")


def role_step(kind: str, rid: str) -> dict:
    bp_role = next((r for r in blueprint()["roles"] if r["id"] == rid), {"id": rid, "labels": {"ar": "دور", "en": rid}})
    return make_step(kind, f"/roles/{rid}", "role", rid, {"definition": bp_role}, impact="access")


def binding_step(eid: str = "customer") -> dict:
    return make_step("binding.add", f"/entities/{eid}/bindings/b1", "binding", "b1",
                     {"definition": {"id": "b1", "component": "core.customer"}}, parents=[("entity", eid)])


def two_fields(a="note_a", b="note_b") -> dict:
    return variant([field_step("customer", a), field_step("customer", b)])
