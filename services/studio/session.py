"""One in-memory Studio session: the working Blueprint, the registry, the engine mapping and one engine site.

Everything is computed on each call with the merged code: compile_blueprint (BPL-004), the adapter harness (BPL-025 fake
by default), resolve_tokens (BRD-004). Nothing is written to disk. All public methods take the session lock."""
from __future__ import annotations

import copy
import json
import re
import threading
import unicodedata
from collections import Counter
from typing import Any, Optional

from . import _paths as P
from .engine import Engine
from compiler import compile_blueprint  # type: ignore  # noqa: E402
from registry import Registry  # type: ignore  # noqa: E402
from tokens import layer_from_css, merge, resolve_tokens  # type: ignore  # noqa: E402
from adapter import testkit as tk  # type: ignore  # noqa: E402

ENVIRONMENT = "sandbox"   # the fixture's manifests are 'tested'; production refuses them (CMP-COMP-003). See question 3.
TENANT = "t_studio"
TENANT_SLUG = "studio-preview"
HEX = re.compile(r"#[0-9A-Fa-f]{6}")
ENTITY_ID = re.compile(r"[a-z][a-z0-9_]{0,63}")
TOKEN_VALUE = re.compile(r"#[0-9A-F]{6}|rgba\(\d{1,3},\d{1,3},\d{1,3},(0|1|0\.\d{1,4})\)")
TEXT_MAX = 200            # contract localizedText maxLength
LOCALES = ("ar", "en")
THEME_KEYS = ("--color-primary", "--color-primary-hover", "--color-primary-pressed", "--color-primary-label",
              "--color-link-visited", "--state-selected", "--state-secondary-hover", "--color-accent",
              "--color-background", "--color-surface", "--color-surface-raised", "--color-text", "--color-text-muted",
              "--color-border", "--color-success", "--color-warning", "--color-danger")
RISK_KEYS = ("total", "maxImpact", "touchesLedgerOrTax", "touchesCompliance", "touchesAccess", "requiresTeamReview",
             "needsDdlPlanGate", "irreversibleSteps")
SECTIONS = ("components", "locations", "entities", "roles", "workflows", "approvals", "reports")


class StudioError(Exception):
    """A refusal with an HTTP status, a stable code and a JSON pointer. Extra keys go into the error object."""

    def __init__(self, status: int, code: str, path: str = "/", **extra: Any):
        super().__init__(code)
        self.status, self.code, self.path, self.extra = status, code, path, extra

    def body(self) -> dict:
        return {"ok": False, "error": {"code": self.code, "path": self.path, **self.extra}}


def _load(path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _issues(result) -> list:
    return [{"code": i.code, "path": i.path or "/", "message": i.message} for i in result.errors]


def check_text(value: Any, path: str) -> str:
    if not isinstance(value, str):
        raise StudioError(400, "STUDIO-TEXT-TYPE", path)
    text = value.strip()
    if not text:
        raise StudioError(400, "STUDIO-TEXT-EMPTY", path)
    if len(text) > TEXT_MAX:
        raise StudioError(400, "STUDIO-TEXT-TOO-LONG", path, max=TEXT_MAX)
    if any(unicodedata.category(ch) in ("Cc", "Cs") for ch in text):
        raise StudioError(400, "STUDIO-TEXT-CONTROL", path)
    return text


def check_localized(value: Any, path: str) -> dict:
    if not isinstance(value, dict):
        raise StudioError(400, "STUDIO-FIELD-TYPE", path)
    for k in value:
        if k not in LOCALES:
            raise StudioError(400, "STUDIO-FIELD-UNKNOWN", f"{path}/{k}")
    for loc in LOCALES:
        if loc not in value:
            raise StudioError(400, "STUDIO-FIELD-MISSING", f"{path}/{loc}")
    return {loc: check_text(value[loc], f"{path}/{loc}") for loc in LOCALES}


def only_keys(body: dict, allowed: tuple, required: tuple = ()) -> None:
    for k in body:
        if k not in allowed:
            raise StudioError(400, "STUDIO-FIELD-UNKNOWN", "/" + k)
    for k in required:
        if k not in body:
            raise StudioError(400, "STUDIO-FIELD-MISSING", "/" + k)


class Session:
    def __init__(self, engine: Engine):
        self.engine = engine
        self._lock = threading.RLock()
        self._fixture = _load(P.FIXTURE)
        self._manifests = [_load(p) for p in sorted(P.REGISTRY_DIR.glob("*.json"))]
        self.registry = Registry.from_manifests(copy.deepcopy(self._manifests))
        self.mapping = _load(P.MAPPING)
        self._base = layer_from_css((P.TOKENS_DIR / "tokens.css").read_text(encoding="utf-8"))
        self._product = layer_from_css((P.TOKENS_DIR / "tokens.proposed.css").read_text(encoding="utf-8"))
        self.reset()

    # ------------------------------------------------------------------ state
    def reset(self) -> dict:
        with self._lock:
            self.blueprint = copy.deepcopy(self._fixture)
            self._all_components = copy.deepcopy(self._fixture["components"])
            self.harness = self.engine.new_harness()
            self.provisioned = False
            self.last_applied: Optional[dict] = None
            return self.state()

    def state(self) -> dict:
        with self._lock:
            bp = self.blueprint
            return {"ok": True, "engine": self.engine.badge(), "environment": ENVIRONMENT,
                    "blueprint": {"id": bp["meta"]["id"], "revision": bp["meta"]["revision"],
                                  "locales": bp["meta"]["locales"], "country": bp["company"].get("country"),
                                  "currency": bp["company"].get("locale", {}).get("currency"),
                                  "legalName": bp["company"]["legalName"], "tradeName": bp["company"]["tradeName"],
                                  "primaryColour": bp["branding"].get("primaryColour"),
                                  "counts": {k: len(bp.get(k, [])) for k in SECTIONS},
                                  "entities": [{"id": e["id"], "labels": e["labels"], "kind": e.get("kind"),
                                                "components": [c["component"] for c in e.get("components", [])]}
                                               for e in bp["entities"]]},
                    "components": self._components_view(), "site": self._site_view()}

    def _manifest(self, cid: str, rng: str) -> Optional[dict]:
        try:
            return self.registry.resolve(cid, rng)
        except ValueError:
            return None

    def _components_view(self) -> list:
        enabled = {c["id"] for c in self.blueprint["components"]}
        manifests = {c["id"]: self._manifest(c["id"], c["versionRange"]) for c in self._all_components}
        providers: dict = {}
        for cid, m in manifests.items():
            for p in (m or {}).get("provides", []):
                if p.get("capability"):
                    providers.setdefault(p["capability"], set()).add(cid)
        requires: dict = {}
        for cid, m in manifests.items():
            need = set()
            for r in (m or {}).get("requires", []):
                need |= {r["component"]} if r.get("component") else providers.get(r.get("capability"), set())
            requires[cid] = sorted(need - {cid})
        out = []
        for c in self._all_components:
            cid, m = c["id"], manifests[c["id"]]
            cert = (m or {}).get("certification", {})
            out.append({"id": cid, "versionRange": c["versionRange"], "enabled": cid in enabled,
                        "name": (m or {}).get("name"), "version": (m or {}).get("version"),
                        "level": cert.get("level"), "touchesLedgerOrTax": bool(cert.get("touchesLedgerOrTax")),
                        "eligible": {env: bool(m) and self.registry.is_eligible(cid, m["version"], env)
                                     for env in ("sandbox", "production")},
                        "requires": requires[cid],
                        "requiredBy": sorted(o for o, need in requires.items() if cid in need and o in enabled),
                        "boundEntities": [e["id"] for e in self.blueprint["entities"]
                                          if any(b.get("component") == cid for b in e.get("components", []))]})
        return out

    # ------------------------------------------------------------------ edits
    def set_company(self, body: dict) -> dict:
        only_keys(body, ("legalName", "tradeName"))
        if not body:
            raise StudioError(400, "STUDIO-FIELD-MISSING", "/legalName")
        values = {k: check_localized(v, "/" + k) for k, v in body.items()}
        with self._lock:
            self.blueprint["company"].update(values)
            return self.state()

    def set_component(self, body: dict) -> dict:
        only_keys(body, ("id", "enabled"), ("id", "enabled"))
        if not isinstance(body["enabled"], bool):
            raise StudioError(400, "STUDIO-FIELD-TYPE", "/enabled")
        with self._lock:
            known = [c["id"] for c in self._all_components]
            if body["id"] not in known:
                raise StudioError(404, "STUDIO-COMPONENT-UNKNOWN", "/id")
            on = {c["id"] for c in self.blueprint["components"]}
            on = on | {body["id"]} if body["enabled"] else on - {body["id"]}
            self.blueprint["components"] = [copy.deepcopy(c) for c in self._all_components if c["id"] in on]
            return self.state()

    def set_entity_labels(self, entity_id: str, body: dict) -> dict:
        if not ENTITY_ID.fullmatch(entity_id):
            raise StudioError(404, "STUDIO-ENTITY-UNKNOWN", "/entities")
        labels = check_localized(body, "")
        with self._lock:
            entity = next((e for e in self.blueprint["entities"] if e["id"] == entity_id), None)
            if entity is None:
                raise StudioError(404, "STUDIO-ENTITY-UNKNOWN", "/entities")
            entity["labels"] = labels
            return self.state()

    def set_branding(self, body: dict) -> dict:
        only_keys(body, ("primaryColour",), ("primaryColour",))
        value = body["primaryColour"]
        if not isinstance(value, str) or not HEX.fullmatch(value):
            raise StudioError(400, "STUDIO-HEX-INVALID", "/primaryColour")
        with self._lock:
            self.blueprint["branding"]["primaryColour"] = value.upper()
            return self.state()

    # ------------------------------------------------------------------ compile
    def _compile(self, bp: dict, registry=None, mapping=None):
        return compile_blueprint(copy.deepcopy(bp), registry or self.registry, copy.deepcopy(mapping or self.mapping),
                                 environment=ENVIRONMENT)

    def compile(self) -> dict:
        with self._lock:
            r = self._compile(self.blueprint)
        if not r.ok:
            return {"ok": False, "refusals": _issues(r)}
        a = r.artifact
        steps = [{"seq": s["seq"], "phase": s["phase"], "kind": s["kind"], "pointer": s["pointer"],
                  "subject": {"kind": s["subject"]["kind"], "id": s["subject"]["id"]},
                  "property": s["params"].get("property"), "impact": s["impact"], "ddlImpact": s["ddlImpact"]}
                 for s in a["steps"]]
        return {"ok": True, "artifactId": a["artifactId"], "stepCount": len(steps), "steps": steps,
                "kinds": dict(sorted(Counter(s["kind"] for s in steps).items())),
                "postConditionCount": len(a["postConditions"]), "skippedOpCount": len(a["skippedOps"]),
                "risk": {k: a["risk"].get(k) for k in RISK_KEYS}, "environment": ENVIRONMENT}

    # ------------------------------------------------------------------ engine
    def _call(self, operation: str, payload: dict, where: str) -> dict:
        resp = self.harness.call(operation, tk.ctx(TENANT), payload)
        if not isinstance(resp, dict) or not resp.get("ok"):
            err = (resp or {}).get("error") or {} if isinstance(resp, dict) else {}
            raise StudioError(502, str(err.get("code") or "STUDIO-ENGINE-ERROR"), where, stage=operation,
                              reasonCode=(err.get("details") or {}).get("reasonCode"))
        return resp["result"]

    def _engine_artifact(self) -> tuple:
        """Re-target a copy for the engine (compiler open question 4) and drop field types it cannot store."""
        adapter_id = self._call("capabilities", {}, "/engine")["adapterId"]
        bp, mp, mans = copy.deepcopy(self.blueprint), copy.deepcopy(self.mapping), copy.deepcopy(self._manifests)
        bp["meta"]["engineTarget"]["adapter"] = mp["engine"]["adapter"] = adapter_id
        for m in mans:
            m["engineCompatibility"]["adapter"] = adapter_id
        dropped = 0
        for e in bp["entities"]:
            keep = [f for f in e["fields"] if f.get("type") not in self.engine.unsupported_field_types]
            dropped, e["fields"] = dropped + len(e["fields"]) - len(keep), keep
        r = self._compile(bp, Registry.from_manifests(mans), mp)
        if not r.ok:
            raise StudioError(409, r.errors[0].code, r.errors[0].path or "/", stage="retarget")
        return r.artifact, dropped

    def _export(self) -> dict:
        return self._call("export_config", {}, "/site")

    def _site_view(self) -> dict:
        if not self.provisioned:
            return {"provisioned": False}
        s = self._call("site_status", {}, "/site")
        applied = s.get("applied") or {}
        return {"provisioned": True, "state": s.get("state"), "appliedArtifactId": applied.get("artifactId"),
                "revision": (applied.get("revision") or {}).get("revision")}

    @staticmethod
    def _outcome(res: dict) -> dict:
        steps = res.get("steps", [])
        pcs = res.get("postConditions", [])
        err = res.get("error") or {}
        return {"status": res.get("status"), "artifactId": res.get("artifactId"),
                "stages": [{"stage": s["stage"], "status": s["status"]} for s in res.get("stages", [])],
                "stepCount": len(steps), "stepStatus": dict(sorted(Counter(s["status"] for s in steps).items())),
                "steps": [{"seq": s["seq"], "status": s["status"]} for s in steps],
                "postConditions": {"total": len(pcs), "passed": sum(1 for p in pcs if p.get("passed")),
                                   "failed": [p["id"] for p in pcs if not p.get("passed")]},
                "error": {"code": err["code"], "stage": err.get("stage"),
                          "path": "/steps/%d" % (err.get("details") or {})["stepSeq"]
                          if isinstance((err.get("details") or {}).get("stepSeq"), int) else "/",
                          "reasonCode": (err.get("details") or {}).get("reasonCode"),
                          "stepSeq": (err.get("details") or {}).get("stepSeq")} if err else None,
                "exportHash": res.get("exportHash")}

    def apply(self, body: dict) -> dict:
        only_keys(body, ("failAtStep",))
        fail_at = body.get("failAtStep")
        if fail_at is not None and (isinstance(fail_at, bool) or not isinstance(fail_at, int) or fail_at < 1):
            raise StudioError(400, "STUDIO-FIELD-TYPE", "/failAtStep")
        with self._lock:
            r = self._compile(self.blueprint)
            if not r.ok:
                return {"ok": False, "stage": "compile", "refusals": _issues(r), "site": self._site_view()}
            art, dropped = self._engine_artifact()
            if fail_at is not None and fail_at > len(art["steps"]):
                raise StudioError(400, "STUDIO-STEP-OUT-OF-RANGE", "/failAtStep", max=len(art["steps"]))
            if not self.provisioned:
                self._call("provision_site", {"idempotencyKey": tk.key(), "engineTarget": copy.deepcopy(art["engineTarget"]),
                                              "countryPack": self.blueprint["compliance"]["countryPack"]["id"],
                                              "siteClass": ENVIRONMENT, "blueprintId": art["blueprint"]["id"]}, "/site")
                self.provisioned = True
            before = self._export()["exportHash"]
            preview = self._call("preview", {"artifact": art}, "/artifact")
            if preview["verdict"] == "rejected":
                raise StudioError(409, "STUDIO-PREVIEW-REJECTED", "/artifact", verdict="rejected")
            plan = self._call("plan", {"artifact": art}, "/artifact")
            approvals = tk.approvals_for(plan, art)
            if fail_at is not None:
                self.harness.fault("execute", step_seq=fail_at)
            res = self._call("apply", {"idempotencyKey": tk.key(), "artifact": art, "planToken": plan["planToken"],
                                       "approvals": approvals}, "/artifact")
            if res.get("status") in ("applied", "already_applied"):
                self.last_applied = art
            after = self._export()["exportHash"]
            out = self._outcome(res)
            out.update(ok=res.get("status") in ("applied", "already_applied"), stage="apply",
                       compiledArtifactId=r.artifact["artifactId"], droppedFields=dropped,
                       verdict=preview["verdict"], approvalsGranted=sorted(approvals),
                       predictedExportHash=preview["predictedExportHash"], exportHashBefore=before, exportHashAfter=after,
                       exportHashMatches=after == preview["predictedExportHash"], site=self._site_view())
            return out

    def rollback(self) -> dict:
        with self._lock:
            if self.last_applied is None:
                raise StudioError(409, "STUDIO-ROLLBACK-NOTHING-APPLIED", "/")
            before = self._export()["exportHash"]
            res = self._call("rollback", {"idempotencyKey": tk.key(), "forwardArtifact": self.last_applied,
                                          "reason": "owner_request", "approvals": {"rollbackApproved": tk.ulid()}},
                             "/forwardArtifact")
            after = self._export()["exportHash"]
            if res.get("status") == "applied":
                self.last_applied = None
            out = self._outcome(res)
            out.update(ok=res.get("status") == "applied", stage="rollback", exportHashBefore=before,
                       exportHashAfter=after, siteChanged=before != after, site=self._site_view())
            return out

    def export_view(self) -> dict:
        with self._lock:
            if not self.provisioned:
                return {"ok": True, "provisioned": False}
            e = self._export()
        ex, sections = e["export"], e["export"]["sections"]
        names = {k: [{"id": x.get("id"), "labels": x.get("labels")} for x in sections.get(k, [])] for k in SECTIONS}
        company = sections.get("settings", {}).get("company", {})
        fields = sum(len(x.get("fields", [])) for x in sections.get("entities", []))
        return {"ok": True, "provisioned": True, "exportHash": e["exportHash"],
                "revision": (ex.get("revision") or {}).get("revision"),
                "counts": {**{k: len(sections.get(k, [])) for k in SECTIONS}, "fields": fields,
                           "settings": sum(len(v) for v in sections.get("settings", {}).values() if isinstance(v, dict))},
                "names": names, "company": {"legalName": company.get("legalName"), "tradeName": company.get("tradeName")},
                "retainedCount": len(e.get("retained") or []), "site": self.state()["site"]}

    # ------------------------------------------------------------------ brand
    def theme(self) -> dict:
        with self._lock:
            branding = copy.deepcopy(self.blueprint["branding"])
        r = resolve_tokens(self._base, self._product, branding, "system", algo_version=1, tenant_slug=TENANT_SLUG)
        platform = merge(self._base, self._product)

        def pick(theme_set: dict) -> dict:
            out = {k: theme_set[k] for k in THEME_KEYS if k in theme_set}
            if any(not TOKEN_VALUE.fullmatch(v) for v in out.values()):
                raise StudioError(500, "STUDIO-TOKEN-VALUE", "/resolved")
            return out

        findings = [f.to_dict() for f in r.findings]
        resolved = {t: pick(r.resolved[t]) for t in ("light", "dark")}
        base = {t: pick(platform[t]) for t in ("light", "dark")}
        return {"ok": r.ok, "input": branding.get("primaryColour"), "themeAlgo": r.theme_algo,
                "resolved": resolved, "platform": base,
                "platformKept": all(resolved[t]["--color-primary"] == base[t]["--color-primary"] for t in resolved),
                "findings": findings,
                "codes": {sev: sorted({f["code"] for f in findings if f["severity"] == sev})
                          for sev in ("refusal", "adjustment", "warning", "notice")}}
