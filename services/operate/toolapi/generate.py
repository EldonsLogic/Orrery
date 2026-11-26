"""generate_tool_api: Blueprint -> typed tool definitions. Pure and deterministic; the input is never mutated."""
from __future__ import annotations

import copy
import re

from . import classify as C
from . import policy as P
from .result import Issue, ToolApiResult, build_set
from .schema import FieldError, field_schema, object_schema

_ID = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
_RANK = {r: i for i, r in enumerate(P.RISK_ORDER)}


def filter_schema(fields: list[str]) -> dict:
    return {"type": "array", "maxItems": 10, "items": object_schema({
        "field": {"type": "string", "enum": fields},
        "op": {"type": "string", "enum": ["eq", "neq", "gt", "gte", "lt", "lte", "in", "not_in", "is_set", "is_not_set"]},
        "value": {"type": ["string", "number", "boolean", "null"]}}, ["field", "op"])}


def _loc(labels) -> dict:
    return {k: v for k, v in sorted(labels.items()) if isinstance(v, str)} if isinstance(labels, dict) else {}


class _Gen:
    def __init__(self, bp: dict, registry: dict | None, manifests: list | None = None, metrics: dict | None = None):
        self.bp = bp
        self.metric_defs = metrics or {}
        self.manifests = manifests
        self.errors: list[Issue] = []
        self.tools: list[dict] = []
        self.registry = registry if registry is not None else {}

    def err(self, code: str, ptr: str, fact: str) -> None:
        self.errors.append(Issue(code, ptr, fact))

    # ---- setup --------------------------------------------------------------------------------------------------
    def setup(self) -> bool:
        bp = self.bp
        self.policy = C.Policy(self.registry, self.manifests)
        self.errors.extend(self.policy.errors)
        if self.policy.errors:
            return False
        if not isinstance(bp, dict) or not isinstance(bp.get("entities"), list) or not isinstance(bp.get("roles"), list):
            self.err("TAPI-INPUT-001", "/", "Blueprint must be an object with entities and roles lists")
            return False
        self.entities: dict[str, dict] = {}
        for i, e in enumerate(bp["entities"]):
            eid = e.get("id") if isinstance(e, dict) else None
            if not isinstance(eid, str) or not _ID.match(eid):
                self.err("TAPI-NAME-004", f"/entities/{i}/id", f"entity id {eid!r} is not a snake_case id")
            elif eid in self.entities:
                self.err("TAPI-NAME-001", f"/entities/{i}/id", f"duplicate entity id {eid!r}")
            elif eid in P.PLATFORM_DOMAINS:
                self.err("TAPI-NAME-002", f"/entities/{i}/id", f"entity id {eid!r} collides with a platform tool domain")
            elif C.identity_entity(eid) or self.policy.permission_entity(eid):
                self.err("TAPI-DOMAIN-001", f"/entities/{i}/id",
                         f"entity id {eid!r} is in the identity and permission domain; such changes are never generated tools")
            else:
                self.entities[eid] = e
        self.cls_of: dict[str, str] = {}
        for eid, e in self.entities.items():
            if e.get("kind") == "child":
                continue
            cls = self.policy.entity_class(eid)
            if cls is None:
                self.err("TAPI-CLASS-001", f"/entities/{eid}",
                         f"entity {eid!r} has no reviewed class (plain, stock or ledger); refused, never assumed plain")
            else:
                self.cls_of[eid] = cls
        self.roles: dict[str, dict] = {}
        for i, r in enumerate(bp["roles"]):
            rid = r.get("id") if isinstance(r, dict) else None
            if not isinstance(rid, str) or not _ID.match(rid) or rid in self.roles:
                self.err("TAPI-NAME-004", f"/roles/{i}/id", f"role id {rid!r} is missing, malformed or duplicated")
            else:
                self.roles[rid] = r
        self.chat_roles = {rid for rid, r in self.roles.items() if r.get("canUseChatActions", True) is not False}
        self.approvals: dict[str, dict] = {}
        for i, a in enumerate(bp.get("approvals") or []):
            aid = a.get("id")
            if aid in self.approvals:
                self.err("TAPI-NAME-001", f"/approvals/{i}/id", f"duplicate approval id {aid!r}")
                continue
            self.approvals[aid] = a
            ap = a.get("appliesTo") or {}
            if ap.get("entity") not in self.entities:
                self.err("TAPI-REF-001", f"/approvals/{i}/appliesTo/entity", f"unknown entity {ap.get('entity')!r}")
            for j, s in enumerate(a.get("steps") or []):
                if s.get("approverRole") not in self.roles:
                    self.err("TAPI-REF-001", f"/approvals/{i}/steps/{j}/approverRole", f"unknown role {s.get('approverRole')!r}")
        self.workflows: dict[str, dict] = {}  # entity id -> workflow
        for i, w in enumerate(bp.get("workflows") or []):
            eid = w.get("entity")
            if eid not in self.entities:
                self.err("TAPI-REF-001", f"/workflows/{i}/entity", f"unknown entity {eid!r}")
            elif eid in self.workflows:
                self.err("TAPI-NAME-001", f"/workflows/{i}/entity", f"entity {eid!r} has more than one workflow")
            elif sum(1 for s in w.get("states") or [] if isinstance(s, dict) and s.get("kind") == "initial") != 1:
                self.err("TAPI-TRANS-002", f"/workflows/{i}/states", "a workflow needs exactly one initial state")
            else:
                self.workflows[eid] = w
        self.revision = (bp.get("meta") or {}).get("revision") if isinstance(bp.get("meta"), dict) else None
        self.perms: dict[tuple[str, str], set[str]] = {}  # (entity, action) -> role ids
        for rid, r in self.roles.items():
            for j, p in enumerate(r.get("permissions") or []):
                if p.get("entity") not in self.entities:
                    self.err("TAPI-REF-001", f"/roles/{rid}/permissions/{j}/entity", f"unknown entity {p.get('entity')!r}")
                    continue
                for a in p.get("actions") or []:
                    self.perms.setdefault((p["entity"], a), set()).add(rid)
        return not self.errors

    # ---- helpers ---------------------------------------------------------------------------------------------------
    def effects(self, eid: str, write: bool) -> dict:
        return self.policy.effects(eid, self.cls_of[eid], write)

    def roles_with(self, eid: str, action: str) -> list[str]:
        return sorted(self.perms.get((eid, action), set()) & self.chat_roles)

    def check_arg_name(self, name: str, ptr: str) -> bool:
        if C.forbidden_arg(name):
            self.err("TAPI-ARG-001", ptr, f"{name!r} would name a caller, role, tenant, user, owner, approver or scope; refused")
            return False
        if name in P.RESERVED_ARG_NAMES:
            self.err("TAPI-NAME-003", ptr, f"{name!r} is reserved by the generator")
            return False
        return True

    def schema_fields(self, entity: dict, eptr: str, nested: bool = False, has_wf: bool = False):
        """-> (input_props, input_required, output_props, sensitive {class: {id: schema}}, required sensitive ids).

        Sensitive fields (bank target, contact, access) never enter the generic inputs: they go to their own R4 tool
        (inside a child table they have no write path at all). Status-like fields are output only.
        """
        ip, ir, op, seen = {}, [], {}, set()
        sens: dict[str, dict] = {}
        sens_req: list[str] = []

        def route(fid, s, required, sc):
            if sc:
                op[fid]["x-sensitive"] = sc
                if not nested:
                    sens.setdefault(sc, {})[fid] = dict(s, **{"x-sensitive": sc})
                    if required:
                        sens_req.append(fid)
                return
            ip[fid] = s
            if required:
                ir.append(fid)

        for j, f in enumerate(entity.get("fields") or []):
            fid, ptr = f.get("id"), f"{eptr}/fields/{j}"
            if not isinstance(fid, str) or not _ID.match(fid) or fid in seen:
                self.err("TAPI-NAME-004", ptr + "/id", f"field id {fid!r} is malformed or duplicated")
                continue
            seen.add(fid)
            if not self.check_arg_name(fid, ptr + "/id"):
                continue
            try:
                s = field_schema(f, set(self.entities))
            except FieldError as exc:
                self.err(exc.code, ptr, f"{fid}: {exc.fact}")
                continue
            op[fid] = copy.deepcopy(s)
            if not f.get("computed") and not f.get("readOnly") and not C.status_like(fid, has_wf):
                route(fid, s, f.get("required") and "default" not in f,
                      C.sensitivity(fid, f.get("type"), f.get("target") if f.get("type") == "link" else None))
        for k, rel in enumerate(entity.get("relations") or []):
            rid, ptr, kind = rel.get("id"), f"{eptr}/relations/{k}", rel.get("kind", "reference")
            if not isinstance(rid, str) or not _ID.match(rid) or rid in seen:
                self.err("TAPI-NAME-004", ptr + "/id", f"relation id {rid!r} is malformed or collides with a field")
                continue
            seen.add(rid)
            if not self.check_arg_name(rid, ptr + "/id"):
                continue
            target = self.entities.get(rel.get("target"))
            if target is None:
                self.err("TAPI-REF-001", ptr + "/target", f"unknown entity {rel.get('target')!r}")
                continue
            many = rel.get("cardinality") == "many"
            if kind == "child_table":
                if nested:
                    self.err("TAPI-REF-002", ptr, "child tables nested inside a child table are not supported")
                    continue
                cip, cir, cop, _, _ = self.schema_fields(target, f"/entities/{rel['target']}", nested=True)
                item_in, item_out = object_schema(cip, cir), object_schema(cop, [])
                arr_in = {"type": "array", "items": item_in, "maxItems": 500}
                if rel.get("required"):
                    arr_in["minItems"] = 1
                ip[rid] = arr_in
                op[rid] = {"type": "array", "items": item_out}
                if rel.get("required"):
                    ir.append(rid)
            else:
                ref = {"type": "string", "pattern": P.ID_PATTERN, "x-entity-ref": rel["target"]}
                s = {"type": "array", "items": ref, "maxItems": 500} if many else ref
                op[rid] = copy.deepcopy(s)
                route(rid, s, bool(rel.get("required")), C.sensitivity(rid, None, rel["target"]))
        return ip, ir, op, sens, sens_req

    def field_access(self, eid: str, roles: list[str]) -> dict:
        entity = self.entities[eid]
        hidden: dict[str, set] = {}
        ro: dict[str, set] = {}
        for rid in roles:
            for p in self.roles[rid].get("permissions") or []:
                if p.get("entity") == eid:
                    hidden.setdefault(rid, set()).update(p.get("hiddenFields") or [])
                    ro.setdefault(rid, set()).update(p.get("readOnlyFields") or [])
            for f in entity.get("fields") or []:
                vis = f.get("visibleToRoles")
                if vis and rid not in vis:
                    hidden.setdefault(rid, set()).add(f.get("id"))
        return {"hidden_by_role": {k: sorted(v) for k, v in sorted(hidden.items()) if v},
                "read_only_by_role": {k: sorted(v) for k, v in sorted(ro.items()) if v}}

    def approval_for(self, eid: str, verbs: tuple, explicit: str | None, risk: str, eff: dict) -> dict:
        ids = set()
        if explicit:
            if explicit in self.approvals:
                ids.add(explicit)
            else:
                self.err("TAPI-REF-001", f"/entities/{eid}", f"approval rule {explicit!r} does not exist")
        for aid, a in self.approvals.items():
            ap = a["appliesTo"]
            if ap.get("entity") == eid and set(verbs) & set(P.APPROVAL_ACTION_VERBS.get(ap.get("action"), ())):
                ids.add(aid)
        rules = sorted(ids)
        approvers = sorted({s["approverRole"] for r in rules for s in self.approvals[r].get("steps") or []})
        return {
            "required": bool(rules), "rule": rules[0] if rules else None, "rules": rules,
            "conditional": any(self.approvals[r].get("conditions") for r in rules),
            "approver_roles": approvers,
            "self_approval": any(self.approvals[r].get("selfApproval") for r in rules),
            "agent_required": bool(rules) or any(eff.values()) or _RANK[risk] >= _RANK["R3"],
        }

    def agent_ok(self, name: str, kind_key: str, risk: str) -> bool:
        return (_RANK[risk] <= _RANK[P.MAX_AGENT_RISK] and kind_key not in P.AGENT_FORBIDDEN_KINDS
                and name not in P.AGENT_FORBIDDEN_TOOLS)

    def labels_for(self, verb: str, labels: dict) -> dict:
        out = {}
        for loc, v in P.VERB_LABELS[verb].items():
            if loc in labels:
                out[loc] = f"{v} {labels[loc]}"
        return out

    def add(self, name, kind, entity, roles, perm, risk, eff, approval, in_schema, out_schema, labels, desc,
            kind_key, extra=None, source_component=None, limits_key=None):
        if not roles:
            return  # contract 3.2: a tool exists only if at least one role may call it
        rk = limits_key or ("read" if kind == "read" else kind)
        limits = dict(P.LIMITS[rk])
        limits["token_budget_class"] = "medium" if name.split(".", 1)[1] in P.MEDIUM_BUDGET_VERBS or name in P.MEDIUM_BUDGET_VERBS else "small"
        t = {
            "name": name, "version": 1, "kind": kind, "labels": labels, "description": desc, "entity": entity,
            "requires": {
                "permission": perm, "roles": roles, "scope": "from_caller",
                "scopes_by_role": {r: copy.deepcopy(self.roles[r].get("scope")) for r in roles},
            },
            "approval": approval, "idempotency": "none" if kind == "read" else "required",
            "input_schema": in_schema, "output_schema": out_schema, "limits": limits, "effects": eff,
            "risk_class": risk, "agent_creatable": self.agent_ok(name, kind_key, risk),
            "source": {"blueprint_revision": self.revision, "component": source_component},
        }
        t.update(extra or {})
        self.tools.append(t)

    def registry_metric_tool(self, none, no_appr) -> None:
        """`metric.query` from the platform metric registry (OPR-006, semantic-layer.md). Roles are the registry's
        roles intersected with the Blueprint's chat roles; the caller's own roles are applied again at run time."""
        roles = {m.id: sorted(set(m.roles) & self.chat_roles) for m in self.metric_defs.values()}
        roles = {k: v for k, v in sorted(roles.items()) if v}
        if not roles:
            return
        value = {"anyOf": [{"type": "string"}, {"type": "integer"}]}
        self.add("metric.query", "read", None, sorted({x for v in roles.values() for x in v}),
                 {"entity": None, "action": "metric.query"}, P.PLATFORM_RISK["metric.query"], dict(none), dict(no_appr),
                 object_schema({"metric": {"type": "string", "enum": sorted(roles)},
                                "period": {"type": "string", "pattern": "^[0-9]{4}-(0[1-9]|1[0-2])$"},
                                "as_of": {"type": "string", "format": "date"},
                                "currency": {"type": "string", "pattern": "^[A-Z]{3}$"}}, ["metric"]),
                 object_schema({"metric": {"type": "string"}, "label_key": {"type": "string"}, "unit": {"type": "string"},
                                "value": value, "currency": {"type": ["string", "null"]}, "params": {"type": "object"}},
                                ["metric", "value"]),
                 {"ar": "استعلام مقياس", "en": "Query a metric"}, "Query a governed metric by id. The value is computed by code.",
                 "metric.query", {"requires_by_value": {"argument": "metric", "roles": roles}})

    # ---- entities --------------------------------------------------------------------------------------------------
    def entity_tools(self, eid: str) -> None:
        e = self.entities[eid]
        eptr = f"/entities/{eid}"
        if e.get("kind") == "child":
            self.schema_fields(e, eptr, nested=True)  # validate types even when no parent embeds it
            return
        has_wf = eid in self.workflows
        ip, ir, op, sens, sens_req = self.schema_fields(e, eptr, has_wf=has_wf)
        cls = self.cls_of[eid]
        for rel in e.get("relations") or []:  # a child table never carries a riskier entity under a cheaper parent
            tgt = rel.get("target")
            tc = self.cls_of.get(tgt) or P.ENTITY_CLASS_DEFAULTS.get(tgt)
            if rel.get("kind") == "child_table" and tc and P.CLASS_RANK[tc] > P.CLASS_RANK[cls]:
                self.err("TAPI-CLASS-003", f"{eptr}/relations/{rel.get('id')}",
                         f"child table {tgt!r} is {tc} class, above its {cls} parent {eid!r}; refused")
                return
        labels = _loc(e.get("labels"))
        en = labels.get("en", eid)
        comp = next((c.get("component") for c in e.get("components") or [] if c.get("mode") == "implements"), None)
        record = object_schema({"id": {"type": "string", "pattern": P.ID_PATTERN}, "version": {"type": "integer", "minimum": 1},
                                **({"state": {"type": "string"}} if has_wf else {}), **op},
                               ["id", "version"])
        id_prop = {"type": "string", "pattern": P.ID_PATTERN}
        ver_prop = {"type": "integer", "minimum": 1}

        def fa(action):
            return self.field_access(eid, self.roles_with(eid, action))

        def mk(verb, in_s, out_s, perm_action, extra=None, kind="write", risk=None, egress=False):
            risk = risk or P.RISK[cls][verb]
            eff = self.effects(eid, kind != "read" and not egress)
            roles = self.roles_with(eid, perm_action)
            appr = self.approval_for(eid, (verb,), None, risk, eff)
            if egress:  # data leaves the platform: a human confirms it, never an agent alone (PI 4.3, A06)
                appr["agent_required"] = True
            labels_ = self.labels_for(verb, labels)
            self.add(f"{eid}.{verb}", kind, eid, roles, {"entity": eid, "action": perm_action}, risk, eff, appr,
                     in_s, out_s, labels_,
                     f"{P.VERB_LABELS[verb]['en']} {en}. Generated from the Blueprint; arguments are typed and checked by code.",
                     verb, {"entity_class": cls, "field_access": fa(perm_action), **(extra or {})}, comp,
                     "export" if egress else None)

        base_filterable = sorted(fid for fid, s in op.items() if s.get("type") not in ("array",) and not s.get("x-attachment"))

        def filterable(action):
            """Fields every role that may call the tool can see: a hidden field is never a filter, sort or group key."""
            hidden = {f for v in fa(action)["hidden_by_role"].values() for f in v}
            return [f for f in base_filterable if f not in hidden]

        mk("get", object_schema({"id": id_prop}, ["id"]), record, "read", kind="read")
        lf = filterable("read")
        mk("list", object_schema({
            "filter": filter_schema(lf), "limit": {"type": "integer", "minimum": 1, "maximum": P.LIMITS["read"]["max_rows"]},
            "cursor": {"type": "string", "maxLength": 512},
            "order_by": object_schema({"field": {"type": "string", "enum": lf},
                                       "direction": {"type": "string", "enum": ["asc", "desc"]}}, ["field"])}, []),
           object_schema({"rows": {"type": "array", "items": record}, "next_cursor": {"type": ["string", "null"]}}, ["rows"]),
           "read", kind="read")
        mk("export", object_schema({"filter": filter_schema(filterable("export")),
                                    "format": {"type": "string", "enum": ["csv", "xlsx"]}}, ["format"]),
           object_schema({"file_id": id_prop, "row_count": {"type": "integer", "minimum": 0}}, ["file_id", "row_count"]),
           "export", egress=True)
        # a required sensitive field must be set at create: that create is then a protected (R4) write as a whole
        req_sens = {f: s for c in sens.values() for f, s in c.items() if f in sens_req}
        mk("create", object_schema({**ip, **req_sens}, ir + sorted(req_sens)), record, "create",
           risk="R4" if req_sens else None)
        mk("update", object_schema({"id": id_prop, "expected_version": ver_prop, **ip}, ["id", "expected_version"]),
           record, "update")
        for sc, verb in P.SENSITIVE_VERBS.items():
            if sc in sens:
                mk(verb, object_schema({"id": id_prop, "expected_version": ver_prop, **sens[sc]},
                                       ["id", "expected_version"]), record, "update")
        mk("delete", object_schema({"id": id_prop, "expected_version": ver_prop}, ["id", "expected_version"]),
           object_schema({"id": id_prop, "deleted": {"type": "boolean", "const": True}}, ["id", "deleted"]), "delete")
        if not has_wf:
            for verb in ("submit", "cancel"):
                mk(verb, object_schema({"id": id_prop, "expected_version": ver_prop,
                                        "reason": {"type": "string", "maxLength": 500}}, ["id", "expected_version"]),
                   record, verb)
        else:
            self.transition_tool(eid, record, labels, en, cls, comp)

    def transition_tool(self, eid, record, labels, en, cls, comp) -> None:
        wf = self.workflows[eid]
        wptr = f"/workflows/{wf.get('id')}"
        states = {s.get("id"): s for s in wf.get("states") or []}
        ts, seen = [], set()
        for k, t in enumerate(wf.get("transitions") or []):
            tid, ptr = t.get("id"), f"{wptr}/transitions/{k}"
            if not isinstance(tid, str) or not _ID.match(tid) or tid in seen:
                self.err("TAPI-NAME-004", ptr + "/id", f"transition id {tid!r} is malformed or duplicated")
                continue
            seen.add(tid)
            if t.get("from") not in states or t.get("to") not in states:
                self.err("TAPI-REF-001", ptr, "transition names a state that does not exist")
                continue
            bad = [r for r in t.get("allowedRoles") or [] if r not in self.roles]
            if bad:
                self.err("TAPI-REF-001", ptr + "/allowedRoles", f"unknown role(s) {bad}")
                continue
            declared = t.get("kind")
            if declared is not None and declared not in P.TRANSITION_KINDS:
                self.err("TAPI-TRANS-001", ptr + "/kind", f"transition kind {declared!r} is not one of {list(P.TRANSITION_KINDS)}")
                continue
            fk, tk = states[t["from"]].get("kind"), states[t["to"]].get("kind")
            kind, forbidden = C.transition_kind(tid, cls, fk, t["to"], tk, bool(t.get("approval")), declared)
            risk = P.RISK[cls][kind]
            eff = self.effects(eid, True)
            roles = sorted(set(t.get("allowedRoles") or []) & self.chat_roles)
            if not roles:
                continue
            # a rule on submit/cancel/update/delete gates a transition whose id names that action, and also, by kind,
            # every move out of the initial state (submit) and every cancel or reversal (cancel)
            verbs = set(C.tokens(tid)) & {"submit", "cancel", "update", "delete"}
            if fk == "initial" and kind in ("advance", "approve"):
                verbs.add("submit")
            if kind in ("cancel", "reversal", "cancel_draft"):
                verbs.add("cancel")
            appr = self.approval_for(eid, ("transition", *sorted(verbs)), t.get("approval"), risk, eff)
            ts.append({
                "id": tid, "from": t["from"], "to": t["to"], "kind": kind, "labels": _loc(t.get("actionLabels")),
                "risk_class": risk,
                "agent_creatable": _RANK[risk] <= _RANK[P.MAX_AGENT_RISK] and not forbidden,
                "allowed_roles": roles, "approval": appr, "guards": copy.deepcopy(t.get("guards") or []),
                "from_state_kind": fk, "to_state_kind": tk, "approval_step": bool(t.get("approval")),
                "declared_kind": declared,
            })
        if not ts:
            return
        risk = max((t["risk_class"] for t in ts), key=_RANK.get)
        eff = self.effects(eid, True)
        roles = sorted({r for t in ts for r in t["allowed_roles"]})
        agent = _RANK[risk] <= _RANK[P.MAX_AGENT_RISK] and any(t["agent_creatable"] for t in ts)
        appr = {"required": any(t["approval"]["required"] for t in ts),
                "rule": None, "rules": sorted({r for t in ts for r in t["approval"]["rules"]}),
                "conditional": any(t["approval"]["conditional"] for t in ts),
                "approver_roles": sorted({r for t in ts for r in t["approval"]["approver_roles"]}),
                "self_approval": any(t["approval"]["self_approval"] for t in ts),
                "agent_required": True, "per_transition": True}
        appr["rule"] = appr["rules"][0] if appr["rules"] else None
        self.add(f"{eid}.transition", "write", eid, roles, {"entity": eid, "action": "transition"}, risk, eff, appr,
                 object_schema({"id": {"type": "string", "pattern": P.ID_PATTERN},
                                "transition_id": {"type": "string", "enum": [t["id"] for t in ts]},
                                "expected_version": {"type": "integer", "minimum": 1},
                                "reason": {"type": "string", "maxLength": 500}},
                               ["id", "transition_id", "expected_version"]),
                 record, self.labels_for("transition", labels),
                 f"Move a {en} through its workflow. Each transition has its own roles, risk class and approval; code checks them.",
                 "transition", {"entity_class": cls, "transitions": ts, "field_access": self.field_access(eid, roles)}, comp)
        # the tool-level flag must agree with the per-transition flags
        self.tools[-1]["agent_creatable"] = agent

    # ---- platform tools ------------------------------------------------------------------------------------------
    def platform_tools(self) -> None:
        bp = self.bp
        none = {k: False for k in P.EFFECT_KEYS}
        no_appr = {"required": False, "rule": None, "rules": [], "conditional": False, "approver_roles": [],
                   "self_approval": False, "agent_required": False}
        reports = bp.get("reports") or []
        rroles: dict[str, list[str]] = {}
        for i, r in enumerate(reports):
            rid = r.get("id")
            if rid in rroles:
                self.err("TAPI-NAME-001", f"/reports/{i}/id", f"duplicate report id {rid!r}")
                continue
            if r.get("entity") is not None and r.get("entity") not in self.entities:
                self.err("TAPI-REF-001", f"/reports/{i}/entity", f"unknown entity {r.get('entity')!r}")
            bad = [x for x in r.get("visibleToRoles") or [] if x not in self.roles]
            if bad:
                self.err("TAPI-REF-001", f"/reports/{i}/visibleToRoles", f"unknown role(s) {bad}")
                continue
            rroles[rid] = sorted(set(r.get("visibleToRoles") or []) & self.chat_roles)
        visible = {k: v for k, v in rroles.items() if v}
        if visible:
            fsch: dict[str, list] = {}
            for r in reports:
                if r.get("id") not in visible:
                    continue
                for f in r.get("filters") or []:
                    s = {"date_range": object_schema({"from": {"type": "string", "format": "date"},
                                                      "to": {"type": "string", "format": "date"}}, []),
                         "number_range": object_schema({"min": {"type": "string", "pattern": "^-?[0-9]{1,18}(\\.[0-9]{1,6})?$"},
                                                        "max": {"type": "string", "pattern": "^-?[0-9]{1,18}(\\.[0-9]{1,6})?$"}}, []),
                         }.get(f.get("type"), {"type": "string", "maxLength": 200 if f.get("type") == "text" else 64})
                    if not isinstance(f, dict) or not isinstance(f.get("field"), str) or not f["field"]:
                        self.err("TAPI-INPUT-003", f"/reports/{r.get('id')}/filters", "a report filter needs a field id")
                        continue
                    if not self.check_arg_name(f["field"], f"/reports/{r.get('id')}/filters"):
                        continue
                    lst = fsch.setdefault(f["field"], [])
                    if s not in lst:
                        lst.append(s)
            fprops = {k: (v[0] if len(v) == 1 else {"anyOf": sorted(v, key=lambda x: repr(sorted(x.items())))})
                      for k, v in sorted(fsch.items())}
            ids = sorted(visible)
            self.add("report.run", "read", None, sorted({x for v in visible.values() for x in v}),
                     {"entity": None, "action": "report.run"}, P.PLATFORM_RISK["report.run"], dict(none), dict(no_appr),
                     object_schema({"report_id": {"type": "string", "enum": ids}, "filters": object_schema(fprops, [])}, ["report_id"]),
                     object_schema({"report_id": {"type": "string"}, "columns": {"type": "array", "items": {"type": "string"}},
                                    "rows": {"type": "array", "items": {"type": "object"}}}, ["report_id", "rows"]),
                     {"ar": "تشغيل تقرير", "en": "Run a report"},
                     "Run a Blueprint report by id. Rows are limited to the caller's scope.", "report.run",
                     {"requires_by_value": {"argument": "report_id", "roles": {k: visible[k] for k in ids}}})
            metrics: dict[str, set] = {}
            group_fields: set[str] = set()
            for r in reports:
                if r.get("id") in visible:
                    for m in r.get("metrics") or []:
                        metrics.setdefault(m.get("ref"), set()).update(visible[r["id"]])
                        for g in m.get("groupBy") or []:
                            if isinstance(g, str) and _ID.match(g) and self.check_arg_name(g, f"/reports/{r['id']}/metrics"):
                                group_fields.add(g)
            group_by = ({"group_by": {"type": "array", "maxItems": 5, "uniqueItems": True,
                                      "items": {"type": "string", "enum": sorted(group_fields)}}} if group_fields else {})
            if metrics and not self.metric_defs:
                self.add("metric.query", "read", None, sorted({x for v in metrics.values() for x in v}),
                         {"entity": None, "action": "metric.query"}, P.PLATFORM_RISK["metric.query"], dict(none), dict(no_appr),
                         object_schema({"metric": {"type": "string", "enum": sorted(metrics)},
                                        **group_by,
                                        "period": object_schema({"from": {"type": "string", "format": "date"}, "to": {"type": "string", "format": "date"}}, [])},
                                       ["metric"]),
                         object_schema({"metric": {"type": "string"}, "rows": {"type": "array", "items": {"type": "object"}}}, ["metric", "rows"]),
                         {"ar": "استعلام مقياس", "en": "Query a metric"}, "Query a semantic-layer metric by id.", "metric.query",
                         {"requires_by_value": {"argument": "metric", "roles": {k: sorted(metrics[k]) for k in sorted(metrics)}}})
        self.registry_metric_tool(none, no_appr)
        if self.approvals:
            approvers = {s["approverRole"] for a in self.approvals.values() for s in a.get("steps") or []}
            approvers |= {r for (e, a), rs in self.perms.items() if a == "approve" for r in rs}
            roles = sorted(approvers & self.chat_roles)
            self.add("approval.list_mine", "read", None, roles, {"entity": None, "action": "approval.list_mine"},
                     P.PLATFORM_RISK["approval.list_mine"],
                     dict(none), dict(no_appr), object_schema({"limit": {"type": "integer", "minimum": 1, "maximum": 200}}, []),
                     object_schema({"rows": {"type": "array", "items": {"type": "object"}}}, ["rows"]),
                     {"ar": "موافقاتي", "en": "My approvals"}, "List approvals waiting for the caller.", "approval.list_mine")
            self.add("approval.decide", "write", None, roles, {"entity": None, "action": "approval.decide"},
                     P.PLATFORM_RISK["approval.decide"], dict(none),
                     dict(no_appr, required=False, agent_required=True),
                     object_schema({"approval_id": {"type": "string", "pattern": P.ID_PATTERN},
                                    "decision": {"type": "string", "enum": ["approve", "reject"]},
                                    "comment": {"type": "string", "maxLength": 500}}, ["approval_id", "decision"]),
                     object_schema({"approval_id": {"type": "string"}, "status": {"type": "string"}}, ["approval_id", "status"]),
                     {"ar": "قرار اعتماد", "en": "Decide an approval"},
                     "Human approvers only. Never reachable from an agent; the requester cannot approve their own request.",
                     "approval.decide")
        admins = sorted({rid for rid, r in self.roles.items() if r.get("isAdmin")} & self.chat_roles)
        self.add("blueprint.propose_change", "admin", None, admins, {"entity": None, "action": "blueprint.propose_change"},
                 P.PLATFORM_RISK["blueprint.propose_change"], dict(none), dict(no_appr, required=True, agent_required=True),
                 object_schema({"base_revision": {"type": "integer", "minimum": 1},
                                "operations": {"type": "array", "minItems": 1, "maxItems": 100, "items": object_schema({
                                    "op": {"type": "string", "enum": ["add", "replace", "remove"]},
                                    "pointer": {"type": "string", "pattern": "^/[A-Za-z0-9_/.~-]{0,200}$"},
                                    "value": {"type": ["string", "number", "boolean", "null"]}}, ["op", "pointer"])}},
                               ["base_revision", "operations"]),
                 object_schema({"proposal_id": {"type": "string"}, "diff_hash": {"type": "string"}}, ["proposal_id", "diff_hash"]),
                 {"ar": "اقتراح تعديل المخطط", "en": "Propose a Blueprint change"},
                 "Produces a diff for human review. Never applies a change.", "blueprint.propose_change")


def generate_tool_api(blueprint, registry=None, manifests=None, metrics=None) -> ToolApiResult:
    """Return the tool set for a validated Blueprint, or a refusal (`ok` False, `errors` set, no tools).

    `registry` is optional L0 configuration: {"source": "<where it came from>", "entity_classes": {entity_id:
    plain|stock|ledger}, "entity_effects": {entity_id: {ledger|tax|external_send: bool}}}. It may only raise a class and
    add effects; an attempt to lower one is refused (TAPI-REGISTRY-002). Its source and hash are recorded in the set.
    `manifests` is an optional list of resolved component manifests whose entity artifacts may declare `riskClass`
    (ADR-0037); same raise-only rule (TAPI-MANIFEST-002), recorded as `manifests`. `metrics` is an optional metric
    registry ({id: definition with .roles}); when given it, not the Blueprint reports, defines `metric.query`. The input is never mutated.
    """
    g = _Gen(blueprint, registry, manifests, metrics)
    if g.setup():
        for eid in sorted(g.entities):
            g.entity_tools(eid)
        g.platform_tools()
    names: dict[str, int] = {}
    for t in g.tools:
        names[t["name"]] = names.get(t["name"], 0) + 1
    for n, c in sorted(names.items()):
        if c > 1:
            g.err("TAPI-NAME-001", f"/tools/{n}", f"tool name {n!r} is produced {c} times")
    g.errors = list(dict.fromkeys(g.errors))
    res = ToolApiResult(errors=g.errors, blueprint_revision=g.revision if not g.errors else None)
    res.registry = getattr(g, "policy", None) and g.policy.meta
    res.manifests = getattr(g, "policy", None) and g.policy.manifest_meta
    if g.errors:
        return res
    tools = sorted(g.tools, key=lambda t: t["name"])
    res.tools = tools
    res.content_hash = build_set(tools, g.revision, res.registry, res.manifests)["contentHash"]
    return res
