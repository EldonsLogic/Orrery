"""generate_tool_api: Blueprint -> typed tool definitions. Pure and deterministic; the input is never mutated."""
from __future__ import annotations

import copy
import re

from . import policy as P
from .result import Issue, ToolApiResult, build_set
from .schema import FieldError, field_schema, object_schema

_ID = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
_RANK = {r: i for i, r in enumerate(P.RISK_ORDER)}


def norm_arg(name: str) -> str:
    return str(name).lower().replace("_", "").replace("-", "")


def _loc(labels) -> dict:
    return {k: v for k, v in sorted(labels.items()) if isinstance(v, str)} if isinstance(labels, dict) else {}


class _Gen:
    def __init__(self, bp: dict, registry: dict | None):
        self.bp = bp
        self.errors: list[Issue] = []
        self.tools: list[dict] = []
        self.registry = registry or {}

    def err(self, code: str, ptr: str, fact: str) -> None:
        self.errors.append(Issue(code, ptr, fact))

    # ---- setup --------------------------------------------------------------------------------------------------
    def setup(self) -> bool:
        bp = self.bp
        reg = self.registry
        if not isinstance(reg, dict) or set(reg) - {"entity_classes", "entity_effects"}:
            self.err("TAPI-REGISTRY-001", "/registry", "registry must be a mapping with only entity_classes and entity_effects")
            return False
        self.classes = dict(P.ENTITY_CLASS_DEFAULTS)
        self.classes.update(reg.get("entity_classes") or {})
        self.effects_extra = {k: dict(v) for k, v in P.ENTITY_EFFECT_DEFAULTS.items()}
        for k, v in (reg.get("entity_effects") or {}).items():
            self.effects_extra[k] = dict(v)
        for k, c in self.classes.items():
            if c not in P.ENTITY_CLASSES:
                self.err("TAPI-REGISTRY-001", f"/registry/entity_classes/{k}", f"unknown entity class {c!r}")
        for k, v in self.effects_extra.items():
            if not isinstance(v, dict) or set(v) - set(P.EFFECT_KEYS) or any(not isinstance(x, bool) for x in v.values()):
                self.err("TAPI-REGISTRY-001", f"/registry/entity_effects/{k}", "effects must be booleans for ledger, tax, external_send")
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
            else:
                self.entities[eid] = e
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
    def eclass(self, eid: str) -> str:
        return self.classes.get(eid, "plain")

    def effects(self, eid: str, write: bool) -> dict:
        eff = {k: False for k in P.EFFECT_KEYS}
        if write:
            if self.eclass(eid) in ("stock", "ledger"):
                eff["ledger"] = True
            eff.update(self.effects_extra.get(eid, {}))
        return eff

    def roles_with(self, eid: str, action: str) -> list[str]:
        return sorted(self.perms.get((eid, action), set()) & self.chat_roles)

    def check_arg_name(self, name: str, ptr: str) -> bool:
        if norm_arg(name) in P.FORBIDDEN_ARG_NAMES:
            self.err("TAPI-ARG-001", ptr, f"{name!r} would be a caller, role, tenant, user or scope argument; refused")
            return False
        if name in P.RESERVED_ARG_NAMES:
            self.err("TAPI-NAME-003", ptr, f"{name!r} is reserved by the generator")
            return False
        return True

    def schema_fields(self, entity: dict, eptr: str, nested: bool = False):
        """-> (input_props, input_required, output_props, output_required, field_ids)"""
        ip, ir, op, orq, seen = {}, [], {}, [], set()
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
            if not f.get("computed") and not f.get("readOnly"):
                ip[fid] = s
                if f.get("required") and "default" not in f:
                    ir.append(fid)
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
                cip, cir, cop, cor, _ = self.schema_fields(target, f"/entities/{rel['target']}", nested=True)
                item_in, item_out = object_schema(cip, cir), object_schema(cop, cor)
                arr_in = {"type": "array", "items": item_in, "maxItems": 500}
                if rel.get("required"):
                    arr_in["minItems"] = 1
                ip[rid] = arr_in
                op[rid] = {"type": "array", "items": item_out}
            else:
                ref = {"type": "string", "pattern": P.ID_PATTERN, "x-entity-ref": rel["target"]}
                s = {"type": "array", "items": ref, "maxItems": 500} if many else ref
                ip[rid], op[rid] = s, copy.deepcopy(s)
            if rel.get("required"):
                ir.append(rid)
        return ip, ir, op, [], seen

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
            kind_key, extra=None, source_component=None):
        if not roles:
            return  # contract 3.2: a tool exists only if at least one role may call it
        rk = "read" if kind == "read" else kind
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

    # ---- entities --------------------------------------------------------------------------------------------------
    def entity_tools(self, eid: str) -> None:
        e = self.entities[eid]
        eptr = f"/entities/{eid}"
        if e.get("kind") == "child":
            self.schema_fields(e, eptr)  # validate types even when no parent embeds it
            return
        ip, ir, op, _, _ = self.schema_fields(e, eptr)
        cls = self.eclass(eid)
        labels = _loc(e.get("labels"))
        en = labels.get("en", eid)
        comp = next((c.get("component") for c in e.get("components") or [] if c.get("mode") == "implements"), None)
        record = object_schema({"id": {"type": "string", "pattern": P.ID_PATTERN}, "version": {"type": "integer", "minimum": 1},
                                **({"state": {"type": "string"}} if eid in self.workflows else {}), **op},
                               ["id", "version"])
        id_prop = {"type": "string", "pattern": P.ID_PATTERN}
        ver_prop = {"type": "integer", "minimum": 1}
        has_wf = eid in self.workflows

        def mk(verb, in_s, out_s, perm_action, extra=None, kind="write"):
            risk = P.RISK[cls][verb]
            eff = self.effects(eid, kind != "read")
            roles = self.roles_with(eid, perm_action)
            self.add(f"{eid}.{verb}", kind, eid, roles, {"entity": eid, "action": perm_action}, risk, eff,
                     self.approval_for(eid, (verb,), None, risk, eff), in_s, out_s, self.labels_for(verb, labels),
                     f"{P.VERB_LABELS[verb]['en']} {en}. Generated from the Blueprint; arguments are typed and checked by code.",
                     verb, extra, comp)

        fa = lambda verb, action: {"field_access": self.field_access(eid, self.roles_with(eid, action))}
        mk("get", object_schema({"id": id_prop}, ["id"]), record, "read", fa("get", "read"), "read")
        filterable = sorted(fid for fid, s in op.items() if s.get("type") not in ("array",) and not s.get("x-attachment"))
        flt = {"type": "array", "maxItems": 10, "items": object_schema({
            "field": {"type": "string", "enum": filterable},
            "op": {"type": "string", "enum": ["eq", "neq", "gt", "gte", "lt", "lte", "in", "not_in", "is_set", "is_not_set"]},
            "value": {"type": ["string", "number", "boolean", "null"]}}, ["field", "op"])}
        mk("list", object_schema({
            "filter": flt, "limit": {"type": "integer", "minimum": 1, "maximum": P.LIMITS["read"]["max_rows"]},
            "cursor": {"type": "string", "maxLength": 512},
            "order_by": object_schema({"field": {"type": "string", "enum": filterable},
                                       "direction": {"type": "string", "enum": ["asc", "desc"]}}, ["field"])}, []),
           object_schema({"rows": {"type": "array", "items": record}, "next_cursor": {"type": ["string", "null"]}}, ["rows"]),
           "read", fa("list", "read"), "read")
        mk("export", object_schema({"filter": flt, "format": {"type": "string", "enum": ["csv", "xlsx"]}}, ["format"]),
           object_schema({"file_id": id_prop, "row_count": {"type": "integer", "minimum": 0}}, ["file_id", "row_count"]),
           "export", fa("export", "export"), "read")
        mk("create", object_schema(ip, ir), record, "create", fa("create", "create"))
        upd = {k: v for k, v in ip.items()}
        mk("update", object_schema({"id": id_prop, "expected_version": ver_prop, **upd}, ["id", "expected_version"]),
           record, "update", fa("update", "update"))
        mk("delete", object_schema({"id": id_prop, "expected_version": ver_prop}, ["id", "expected_version"]),
           object_schema({"id": id_prop, "deleted": {"type": "boolean", "const": True}}, ["id", "deleted"]), "delete")
        if not has_wf:
            for verb in ("submit", "cancel"):
                mk(verb, object_schema({"id": id_prop, "expected_version": ver_prop,
                                        "reason": {"type": "string", "maxLength": 500}}, ["id", "expected_version"]),
                   record, verb, fa(verb, verb))
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
            kind = "advance"
            toks = set(tid.split("_"))
            for tok, k2 in P.TRANSITION_TOKENS:
                if tok in toks:
                    kind = k2
                    break
            if kind == "cancel" and states[t["from"]].get("kind") == "initial":
                kind = "cancel_draft"
            risk = P.RISK[cls][kind]
            eff = self.effects(eid, True)
            roles = sorted(set(t.get("allowedRoles") or []) & self.chat_roles)
            if not roles:
                continue
            # a rule on submit/cancel/update/delete also gates a transition whose id names that action
            appr = self.approval_for(eid, ("transition", *sorted(toks & {"submit", "cancel", "update", "delete"})),
                                     t.get("approval"), risk, eff)
            ts.append({
                "id": tid, "from": t["from"], "to": t["to"], "kind": kind, "labels": _loc(t.get("actionLabels")),
                "risk_class": risk, "agent_creatable": self.agent_ok(f"{eid}.transition", kind, risk),
                "allowed_roles": roles, "approval": appr, "guards": copy.deepcopy(t.get("guards") or []),
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
                 "transition", {"transitions": ts, "field_access": self.field_access(eid, roles)}, comp)
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
                    if not self.check_arg_name(f.get("field", ""), f"/reports/{r.get('id')}/filters"):
                        continue
                    lst = fsch.setdefault(f["field"], [])
                    if s not in lst:
                        lst.append(s)
            fprops = {k: (v[0] if len(v) == 1 else {"anyOf": sorted(v, key=lambda x: repr(sorted(x.items())))})
                      for k, v in sorted(fsch.items())}
            ids = sorted(visible)
            self.add("report.run", "read", None, sorted({x for v in visible.values() for x in v}),
                     {"entity": None, "action": "report.run"}, "R0", dict(none), dict(no_appr),
                     object_schema({"report_id": {"type": "string", "enum": ids}, "filters": object_schema(fprops, [])}, ["report_id"]),
                     object_schema({"report_id": {"type": "string"}, "columns": {"type": "array", "items": {"type": "string"}},
                                    "rows": {"type": "array", "items": {"type": "object"}}}, ["report_id", "rows"]),
                     {"ar": "تشغيل تقرير", "en": "Run a report"},
                     "Run a Blueprint report by id. Rows are limited to the caller's scope.", "report.run",
                     {"requires_by_value": {"argument": "report_id", "roles": {k: visible[k] for k in ids}}})
            metrics: dict[str, set] = {}
            for r in reports:
                if r.get("id") in visible:
                    for m in r.get("metrics") or []:
                        metrics.setdefault(m.get("ref"), set()).update(visible[r["id"]])
            if metrics:
                self.add("metric.query", "read", None, sorted({x for v in metrics.values() for x in v}),
                         {"entity": None, "action": "metric.query"}, "R0", dict(none), dict(no_appr),
                         object_schema({"metric": {"type": "string", "enum": sorted(metrics)},
                                        "group_by": {"type": "array", "maxItems": 5, "items": {"type": "string", "pattern": "^[a-z][a-z0-9_]{1,63}$"}},
                                        "period": object_schema({"from": {"type": "string", "format": "date"}, "to": {"type": "string", "format": "date"}}, [])},
                                       ["metric"]),
                         object_schema({"metric": {"type": "string"}, "rows": {"type": "array", "items": {"type": "object"}}}, ["metric", "rows"]),
                         {"ar": "استعلام مقياس", "en": "Query a metric"}, "Query a semantic-layer metric by id.", "metric.query",
                         {"requires_by_value": {"argument": "metric", "roles": {k: sorted(metrics[k]) for k in sorted(metrics)}}})
        if self.approvals:
            approvers = {s["approverRole"] for a in self.approvals.values() for s in a.get("steps") or []}
            approvers |= {r for (e, a), rs in self.perms.items() if a == "approve" for r in rs}
            roles = sorted(approvers & self.chat_roles)
            self.add("approval.list_mine", "read", None, roles, {"entity": None, "action": "approval.list_mine"}, "R0",
                     dict(none), dict(no_appr), object_schema({"limit": {"type": "integer", "minimum": 1, "maximum": 200}}, []),
                     object_schema({"rows": {"type": "array", "items": {"type": "object"}}}, ["rows"]),
                     {"ar": "موافقاتي", "en": "My approvals"}, "List approvals waiting for the caller.", "approval.list_mine")
            self.add("approval.decide", "write", None, roles, {"entity": None, "action": "approval.decide"}, "R3", dict(none),
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
                 "R4", dict(none), dict(no_appr, required=True, agent_required=True),
                 object_schema({"base_revision": {"type": "integer", "minimum": 1},
                                "operations": {"type": "array", "minItems": 1, "maxItems": 100, "items": object_schema({
                                    "op": {"type": "string", "enum": ["add", "replace", "remove"]},
                                    "pointer": {"type": "string", "pattern": "^/[A-Za-z0-9_/.~-]{0,200}$"},
                                    "value": {"type": ["string", "number", "boolean", "null"]}}, ["op", "pointer"])}},
                               ["base_revision", "operations"]),
                 object_schema({"proposal_id": {"type": "string"}, "diff_hash": {"type": "string"}}, ["proposal_id", "diff_hash"]),
                 {"ar": "اقتراح تعديل المخطط", "en": "Propose a Blueprint change"},
                 "Produces a diff for human review. Never applies a change.", "blueprint.propose_change")


def generate_tool_api(blueprint, registry=None) -> ToolApiResult:
    """Return the tool set for a validated Blueprint, or a refusal (`ok` False, `errors` set, no tools).

    `registry` is optional: {"entity_classes": {entity_id: plain|stock|ledger}, "entity_effects": {entity_id:
    {ledger|tax|external_send: bool}}}. It adds to the policy defaults. The input is never mutated.
    """
    g = _Gen(blueprint, registry)
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
    if g.errors:
        return res
    tools = sorted(g.tools, key=lambda t: t["name"])
    res.tools = tools
    res.content_hash = build_set(tools, g.revision)["contentHash"]
    return res
