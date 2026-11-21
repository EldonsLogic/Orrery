"""SEC-022 and BPL-032 (ADR-0051): adapter-owned role and state names, and mapped permission rules.

Runs offline on CaseInsensitiveEngine, a simulated engine whose record names match without case like the
real one (MariaDB `utf8mb4_unicode_ci`). Fail closed throughout: a collision refuses the step before any
write; a grant the adapter cannot enforce faithfully is withheld, never widened. Synthetic data only.
"""
from __future__ import annotations

import os
import unittest
from unittest import mock

from change_engine.adapter import FrappeBackendError, FrappeRuntimeBackend, FrappeSiteResolver
from change_engine.adapter.mapping import ENGINE_NAME_PREFIX, EngineNameError, engine_role_name, engine_state_name
from change_engine.guarded_apply.workflow_engine import execute_workflow_deployment
from change_engine.tests.ci_engine_fake import BUILTIN_ROLES, BUILTIN_STATES, STANDARD_PERMS, CaseInsensitiveEngine

TENANT = "t_sec022"
SITE = "ci.localhost"
FLAGS = ("read", "write", "create", "delete", "submit", "cancel", "amend", "report", "export", "import", "share",
         "print", "email", "set_user_permissions")


def step(kind: str, sid: str, defn: dict | None = None, section: str = "roles") -> dict:
    return {"seq": 1, "kind": kind, "pointer": f"/{section}/{sid}", "subject": {"kind": section[:-1], "id": sid},
            "params": {"definition": defn} if defn is not None else {}}


def role(rid: str, perms: list[dict], scope: str = "company") -> dict:
    return {"id": rid, "labels": {"en": rid, "ar": rid}, "scope": {"type": scope}, "permissions": perms}


def grant(entity: str, *actions: str, hidden: tuple[str, ...] = (), read_only: tuple[str, ...] = ()) -> dict:
    g: dict = {"entity": entity, "actions": list(actions)}
    if hidden:
        g["hiddenFields"] = list(hidden)
    if read_only:
        g["readOnlyFields"] = list(read_only)
    return g


class _Base(unittest.TestCase):
    def setUp(self) -> None:
        env = mock.patch.dict(os.environ, {"CHANGE_ENGINE_ENV": "test"})
        env.start()
        self.addCleanup(env.stop)
        self.engine = CaseInsensitiveEngine(SITE)
        self.backend = FrappeRuntimeBackend(
            site_resolver=FrappeSiteResolver(site_map={TENANT: SITE}),
            frappe_factory=lambda: self.engine,
            offline_ddl_simulator=True,
        )

    def run_step(self, st: dict) -> None:
        self.backend.execute_step(TENANT, st)

    def upsert(self, defn: dict) -> None:
        self.run_step(step("role.upsert", defn["id"], defn))

    def add_entity(self, eid: str, *field_ids: str) -> None:
        fields = [{"id": fid, "type": "string", "labels": {"en": fid, "ar": fid}} for fid in field_ids]
        self.run_step(step("entity.add", eid, {"id": eid, "fields": fields}, section="entities"))

    def roles(self) -> dict[str, dict]:
        return {r["name"]: r for r in self.engine.rows("Role")}

    def rules(self, role_name: str | None = None, doctype: str | None = None) -> dict[tuple[str, str, int], dict]:
        """Managed (or given role's) permission rules as {(role, doctype, level): {flag: value}}."""
        out = {}
        for r in self.engine.rows("Custom DocPerm"):
            if role_name is not None and r.get("role") != role_name:
                continue
            if doctype is not None and r.get("parent") != doctype:
                continue
            key = (r["role"], r["parent"], int(r.get("permlevel") or 0))
            self.assertNotIn(key, out, f"duplicate rule {key}")
            out[key] = {k: int(r.get(k) or 0) for k in (*FLAGS, "if_owner")}
        return out

    def granted(self, role_name: str, doctype: str, level: int = 0) -> set[str]:
        row = self.rules(role_name, doctype).get((role_name, doctype, level), {})
        return {k for k, v in row.items() if v and k != "if_owner"}

    def level(self, doctype: str, fieldname: str) -> int:
        return int(getattr(self.engine.get_meta(doctype).get_field(fieldname), "permlevel", 0) or 0)

    def refused(self, fn, code: str = "plan_rejected", reason: str | None = "protected_subject") -> FrappeBackendError:
        with self.assertRaises(FrappeBackendError) as err:
            fn()
        self.assertEqual(err.exception.code, code)
        if reason is not None:
            self.assertEqual(err.exception.details.get("reasonCode"), reason)
        self.assertTrue(err.exception.side_effect_free, "a refusal must happen before any write")
        return err.exception


class TestEngineNames(unittest.TestCase):
    def test_names_are_prefixed_and_reversible(self) -> None:
        self.assertEqual(engine_role_name("auditor"), "bp-auditor")
        self.assertEqual(engine_state_name("approved"), "bp-approved")
        self.assertEqual(ENGINE_NAME_PREFIX, "bp-")

    def test_only_blueprint_ids_are_accepted(self) -> None:
        for bad in ("Auditor", "", "a", "bp-auditor", "a" * 65, "1abc", "has space", None, 7):
            with self.assertRaises(EngineNameError, msg=repr(bad)):
                engine_role_name(bad)  # type: ignore[arg-type]

    def test_no_managed_name_can_equal_a_builtin_or_a_raw_blueprint_id(self) -> None:
        # The prefix holds '-', which the Blueprint id grammar forbids, so a raw id never equals a managed name.
        for name in (*BUILTIN_ROLES, *BUILTIN_STATES):
            raw = name.lower().replace(" ", "_")
            self.assertNotEqual(engine_role_name(raw).casefold(), name.casefold())
            self.assertIn("-", engine_role_name(raw))


class TestSec022RoleNamespacing(_Base):
    def test_role_upsert_auditor_creates_a_managed_role_and_leaves_the_builtin_alone(self) -> None:
        before = self.roles()["Auditor"]
        self.upsert(role("auditor", [grant("customer", "read")]))
        roles = self.roles()
        self.assertEqual(roles["bp-auditor"]["disabled"], 0)
        self.assertEqual(roles["Auditor"], before)
        self.assertEqual(self.granted("Auditor", "Customer"), {"read"}, "the built-in keeps exactly its standard rule")
        self.assertEqual(self.granted("bp-auditor", "Customer"), {"read"})

    def test_administrator_all_guest_and_system_manager_never_resolve_to_builtins(self) -> None:
        before = {k: v for k, v in self.roles().items() if k in BUILTIN_ROLES}
        for rid in ("administrator", "all", "guest", "system_manager"):
            self.upsert(role(rid, [grant("customer", "read")]))
        after = self.roles()
        self.assertEqual({k: after[k] for k in BUILTIN_ROLES}, before)
        for rid in ("administrator", "all", "guest", "system_manager"):
            self.assertIn(engine_role_name(rid), after)

    def test_case_variant_of_a_managed_name_held_by_someone_else_is_refused(self) -> None:
        self.engine.current_site_db().rows["tabRole"]["BP-Auditor"] = {"doctype": "Role", "name": "BP-Auditor", "role_name": "BP-Auditor", "disabled": 1}
        self.refused(lambda: self.upsert(role("auditor", [grant("customer", "read")])))
        self.assertEqual(self.roles()["BP-Auditor"]["disabled"], 1, "the other role was not re-enabled")
        self.assertEqual(self.rules("BP-Auditor"), {})

    def test_role_disable_only_touches_the_managed_role(self) -> None:
        self.upsert(role("auditor", [grant("customer", "read")]))
        self.run_step(step("role.disable", "auditor"))
        roles = self.roles()
        self.assertEqual(roles["bp-auditor"]["disabled"], 1)
        self.assertEqual(roles["Auditor"]["disabled"], 0)

    def test_sync_members_assigns_managed_roles(self) -> None:
        self.upsert(role("sales_rep", [grant("customer", "read")]))
        listed = {"m_rep001": {"status": "active", "roleIds": ["sales_rep"]}}
        self.backend.sync_members(TENANT, [{"memberRef": "m_rep001"}], "delta", listed)
        users = self.engine.rows("User")
        self.assertEqual(len(users), 1)
        self.assertEqual(users[0]["roles"], [{"role": "bp-sales_rep"}])

    def test_sync_members_refuses_unknown_colliding_or_disabled_roles_and_changes_nobody(self) -> None:
        self.upsert(role("sales_rep", [grant("customer", "read")]))
        self.upsert(role("old_role", [grant("customer", "read")]))
        self.run_step(step("role.disable", "old_role"))
        site = self.engine.current_site_db()
        site.rows["tabRole"]["BP-Clerk"] = {"doctype": "Role", "name": "BP-Clerk", "role_name": "BP-Clerk", "disabled": 0}
        roles_before = self.roles()
        for bad in ("auditor", "administrator", "clerk", "old_role"):
            listed = {"m_ok00001": {"status": "active", "roleIds": ["sales_rep"]}, "m_bad0001": {"status": "active", "roleIds": [bad]}}
            self.refused(lambda: self.backend.sync_members(TENANT, [{"memberRef": "m_ok00001"}, {"memberRef": "m_bad0001"}], "delta", listed),
                         code="unknown_role", reason=None)
            self.assertEqual(self.engine.rows("User"), [], f"{bad}: no member may change")
        self.assertEqual(self.roles(), roles_before, "sync_members never creates roles")

    def test_workflow_states_and_transition_roles_are_namespaced(self) -> None:
        self.upsert(role("sales_rep", [grant("sales_order", "read", "update")]))
        self.upsert(role("owner", [grant("sales_order", "read", "update")]))
        self.run_step(step("workflow.upsert", "so_flow", {
            "id": "so_flow", "entity": "sales_order",
            "states": [{"id": "draft", "kind": "initial"}, {"id": "approved", "kind": "final"}, {"id": "cancelled", "kind": "final"}],
            "transitions": [
                {"id": "approve", "from": "draft", "to": "approved", "allowedRoles": ["owner"], "actionLabels": {"en": "Approve"}},
                {"id": "cancel", "from": "draft", "to": "cancelled", "allowedRoles": ["sales_rep", "owner"], "actionLabels": {"en": "Cancel"}},
            ],
        }, section="workflows"))
        wf = self.engine.get_doc("Workflow", "so_flow")
        self.assertEqual(sorted(s["state"] for s in wf.states), ["bp-approved", "bp-cancelled", "bp-draft"])
        self.assertEqual({s["allow_edit"] for s in wf.states if s["state"] == "bp-draft"}, {"bp-owner"})
        self.assertEqual(sorted((t["state"], t["next_state"], t["allowed"]) for t in wf.transitions), [
            ("bp-draft", "bp-approved", "bp-owner"), ("bp-draft", "bp-cancelled", "bp-owner"), ("bp-draft", "bp-cancelled", "bp-sales_rep")])
        states = {r["name"] for r in self.engine.rows("Workflow State")}
        self.assertTrue({"bp-draft", "bp-approved", "bp-cancelled"} <= states)
        self.assertTrue(set(BUILTIN_STATES) <= states)

    def test_workflow_state_case_collision_is_refused_before_any_write(self) -> None:
        self.upsert(role("owner", [grant("sales_order", "read", "update")]))
        site = self.engine.current_site_db()
        site.rows["tabWorkflow State"]["BP-Approved"] = {"doctype": "Workflow State", "name": "BP-Approved", "workflow_state_name": "BP-Approved"}
        before = {t: len(site.rows.get(t, {})) for t in ("tabWorkflow", "tabWorkflow State", "tabWorkflow Action Master")}
        self.refused(lambda: self.run_step(step("workflow.upsert", "so_flow", {
            "id": "so_flow", "entity": "sales_order",
            "states": [{"id": "draft", "kind": "initial"}, {"id": "approved", "kind": "final"}],
            "transitions": [{"id": "approve", "from": "draft", "to": "approved", "allowedRoles": ["owner"], "actionLabels": {"en": "Approve"}}],
        }, section="workflows")))
        self.assertEqual({t: len(site.rows.get(t, {})) for t in before}, before)

    def test_workflow_refusal_happens_before_the_document_type_is_created(self) -> None:
        site = self.engine.current_site_db()
        site.rows["tabWorkflow State"]["BP-Done"] = {"doctype": "Workflow State", "name": "BP-Done", "workflow_state_name": "BP-Done"}
        doctypes = set(site.rows.get("tabDocType", {}))
        for to_state in ("done", "Done"):  # a case collision, then a transition target that is not a Blueprint id
            self.refused(lambda: self.run_step(step("workflow.upsert", "gizmo_flow", {
                "id": "gizmo_flow", "entity": "gizmo",
                "states": [{"id": "draft", "kind": "initial"}],
                "transitions": [{"id": "finish", "from": "draft", "to": to_state, "actionLabels": {"en": "Finish"}}],
            }, section="workflows")), reason="protected_subject" if to_state == "done" else "unsupported_value_type")
            self.assertEqual(set(site.rows.get("tabDocType", {})), doctypes, to_state)
            self.assertFalse(self.engine.db.table_exists("Gizmo"))

    def test_workflow_or_report_naming_a_colliding_role_is_refused(self) -> None:
        site = self.engine.current_site_db()
        site.rows["tabRole"]["BP-Owner"] = {"doctype": "Role", "name": "BP-Owner", "role_name": "BP-Owner", "disabled": 0}
        self.refused(lambda: self.run_step(step("report.upsert", "sales_overview", {
            "id": "sales_overview", "entity": "sales_order", "visibleToRoles": ["owner"]}, section="reports")))
        self.assertEqual(self.engine.rows("Report"), [])

    def test_report_roles_are_namespaced(self) -> None:
        self.upsert(role("owner", [grant("sales_order", "read")]))
        self.run_step(step("report.upsert", "sales_overview", {
            "id": "sales_overview", "entity": "sales_order", "visibleToRoles": ["owner"]}, section="reports"))
        (rep,) = self.engine.rows("Report")
        self.assertEqual([r["role"] for r in rep["roles"]], ["bp-owner"])


class TestWorkflowEngineStateCollisionGate(unittest.TestCase):
    def _db(self, stored: dict[str, str]) -> mock.MagicMock:
        db = mock.MagicMock()
        db.get_workflow_state.side_effect = lambda name: {"name": stored[name.casefold()]} if name.casefold() in stored else None
        db.acquire_advisory_lock.return_value = 1
        db.get_existing_deployment_by_idempotency.return_value = None
        db.is_target_in_recovery_required.return_value = False
        db.get_active_workflow.return_value = None
        return db

    def _wf(self, *states: str) -> dict:
        return {"workflow_name": "wf", "document_type": "Sales Order",
                "states": [{"state": states[0], "doc_status": 0, "allow_edit": "System Manager"},
                           {"state": states[1], "doc_status": 1, "allow_edit": "System Manager", "is_terminal": True}],
                "transitions": [{"state": states[0], "action": "Go", "next_state": states[1], "allowed": "System Manager"}]}

    def test_case_variant_state_is_refused_before_lock_and_journal(self) -> None:
        db = self._db({"approved": "Approved"})
        out = execute_workflow_deployment(db, "dep1", TENANT, "Sales Order", self._wf("bp-draft", "approved"), user_roles=["System Manager"])
        self.assertEqual((out["status"], out["disposition"]), ("REJECTED", "WORKFLOW_STATE_NAME_COLLISION"))
        db.acquire_advisory_lock.assert_not_called()
        db.persist_prepare_and_audit_intent.assert_not_called()

    def test_exact_existing_state_is_reused(self) -> None:
        db = self._db({"approved": "Approved"})
        out = execute_workflow_deployment(db, "dep2", TENANT, "Sales Order", self._wf("Draft", "Approved"), user_roles=["System Manager"])
        self.assertNotEqual(out.get("disposition"), "WORKFLOW_STATE_NAME_COLLISION")
        db.acquire_advisory_lock.assert_called_once()


class TestBpl032RoleGrants(_Base):
    def test_action_table_and_engine_dependencies(self) -> None:
        self.upsert(role("owner", [grant("sales_order", "read", "create", "update", "submit", "cancel", "approve", "export", "delete")]))
        self.assertEqual(self.granted("bp-owner", "Sales Order"),
                         {"read", "create", "write", "submit", "cancel", "amend", "export", "delete"})

    def test_flags_the_engine_cannot_hold_are_dropped_not_widened(self) -> None:
        self.upsert(role("clerk", [
            grant("sales_order", "read", "update", "cancel"),   # cancel needs submit
            grant("sales_invoice", "read", "submit"),           # submit needs write
            grant("customer", "read", "update", "submit"),      # Customer is not submittable
            grant("item", "create", "update"),                  # no read: nothing at all
        ]))
        self.assertEqual(self.granted("bp-clerk", "Sales Order"), {"read", "write"})
        self.assertEqual(self.granted("bp-clerk", "Sales Invoice"), {"read"})
        self.assertEqual(self.granted("bp-clerk", "Customer"), {"read", "write"})
        self.assertEqual(self.rules("bp-clerk", "Item"), {})

    def test_never_granted_flags_stay_off(self) -> None:
        self.upsert(role("owner", [grant("customer", "read", "create", "update", "delete", "export")]))
        row = self.rules("bp-owner", "Customer")[("bp-owner", "Customer", 0)]
        for flag in ("report", "print", "share", "import", "email", "set_user_permissions", "submit", "cancel", "amend"):
            self.assertEqual(row[flag], 0, flag)

    def test_own_records_scope_sets_owner_only(self) -> None:
        self.upsert(role("sales_rep", [grant("sales_order", "read", "create", "update")], scope="own_records"))
        self.assertEqual(self.rules("bp-sales_rep")[("bp-sales_rep", "Sales Order", 0)]["if_owner"], 1)

    def test_location_scopes_are_withheld_until_record_scoping_exists(self) -> None:
        for scope in ("branch", "warehouse", "department"):
            self.upsert(role(f"r_{scope}", [grant("sales_order", "read", "update")], scope=scope))
            self.assertEqual(self.rules(engine_role_name(f"r_{scope}")), {}, scope)
            self.assertEqual(self.roles()[engine_role_name(f"r_{scope}")]["disabled"], 0)

    def test_assigned_records_and_protected_or_missing_entities_are_refused(self) -> None:
        self.refused(lambda: self.upsert(role("r_assigned", [grant("sales_order", "read")], scope="assigned_records")),
                     reason="unsupported_value_type")
        self.refused(lambda: self.upsert(role("r_ledger", [grant("general_ledger", "read")])))
        self.refused(lambda: self.upsert(role("r_ghost", [grant("no_such_thing", "read")])), reason="subject_missing")
        self.assertNotIn("bp-r_assigned", self.roles())

    def test_masked_grant_withholds_create_and_write(self) -> None:
        self.add_entity("widget", "cost", "note")
        self.upsert(role("clerk", [grant("widget", "read", "create", "update", "delete", read_only=("note",))]))
        self.assertEqual(self.granted("bp-clerk", "Widget"), {"read", "delete"})

    def test_unresolved_hidden_field_withholds_the_whole_entity_grant(self) -> None:
        self.upsert(role("sales_rep", [grant("customer", "read", hidden=("credit_limit",)), grant("sales_order", "read")]))
        self.assertEqual(self.rules("bp-sales_rep", "Customer"), {})
        self.assertEqual(self.granted("bp-sales_rep", "Sales Order"), {"read"})

    def test_standard_rules_of_builtin_roles_are_kept(self) -> None:
        self.upsert(role("owner", [grant("customer", "read", "update")]))
        for perm in STANDARD_PERMS:
            if perm["parent"] == "Customer":
                want = {k for k in FLAGS if perm.get(k)}
                self.assertEqual(self.granted(perm["role"], "Customer"), want, perm["role"])

    def test_upsert_is_idempotent_and_dropping_an_entity_clears_its_rules(self) -> None:
        defn = role("owner", [grant("customer", "read", "update"), grant("item", "read")])
        self.upsert(defn)
        once = self.rules()
        self.upsert(defn)
        self.assertEqual(self.rules(), once)
        self.upsert(role("owner", [grant("customer", "read", "update")]))
        self.assertEqual(self.granted("bp-owner", "Item"), set())
        self.assertEqual(self.granted("bp-owner", "Customer"), {"read", "write"})

    def test_role_disable_removes_every_rule_and_reupsert_restores(self) -> None:
        defn = role("owner", [grant("customer", "read", "update")])
        self.upsert(defn)
        self.run_step(step("role.disable", "owner"))
        self.assertTrue(all(not any(v for k, v in row.items() if k != "if_owner") for row in self.rules("bp-owner").values()))
        self.upsert(defn)
        self.assertEqual(self.roles()["bp-owner"]["disabled"], 0)
        self.assertEqual(self.granted("bp-owner", "Customer"), {"read", "write"})


class TestBpl032FieldLevels(_Base):
    ROLES = (
        role("full", [grant("widget", "read", "update")]),
        role("viewer", [grant("widget", "read")]),
        role("hider", [grant("widget", "read", hidden=("cost",))]),
        role("hider2", [grant("widget", "read", hidden=("cost", "note"))]),
    )

    def setUp(self) -> None:
        super().setUp()
        self.add_entity("widget", "cost", "note", "title_text")

    def visibility(self) -> dict[str, dict[str, set[str]]]:
        """Per role: which widget fields it can read and write, from the rules and field levels alone."""
        out: dict[str, dict[str, set[str]]] = {}
        for rid in ("full", "viewer", "hider", "hider2"):
            name = engine_role_name(rid)
            rules = self.rules(name, "Widget")
            seen = {"read": set(), "write": set()}
            for fn in ("custom_cost", "custom_note", "custom_title_text"):
                row = rules.get((name, "Widget", self.level("Widget", fn)), {})
                for flag in seen:
                    if row.get(flag) and rules.get((name, "Widget", 0), {}).get(flag):
                        seen[flag].add(fn)
            out[rid] = seen
        return out

    def expected_visibility(self) -> dict[str, dict[str, set[str]]]:
        every = {"custom_cost", "custom_note", "custom_title_text"}
        return {
            "full": {"read": every, "write": every},
            "viewer": {"read": every, "write": set()},
            "hider": {"read": every - {"custom_cost"}, "write": set()},
            "hider2": {"read": {"custom_title_text"}, "write": set()},
        }

    def test_hidden_fields_get_their_own_levels(self) -> None:
        for defn in self.ROLES:
            self.upsert(defn)
        self.assertEqual(self.visibility(), self.expected_visibility())
        self.assertEqual(self.level("Widget", "custom_title_text"), 0)
        levels = {self.level("Widget", "custom_cost"), self.level("Widget", "custom_note")}
        self.assertEqual(len(levels), 2)
        self.assertTrue(levels <= set(range(1, 10)))

    def test_layout_does_not_depend_on_role_order(self) -> None:
        for defn in reversed(self.ROLES):
            self.upsert(defn)
        self.assertEqual(self.visibility(), self.expected_visibility())

    def test_reupsert_is_a_noop(self) -> None:
        for defn in self.ROLES:
            self.upsert(defn)
        rules, setters = self.rules(), self.engine.rows("Property Setter")
        for defn in self.ROLES:
            self.upsert(defn)
        self.assertEqual(self.rules(), rules)
        self.assertEqual(self.engine.rows("Property Setter"), setters)

    def test_unhiding_returns_fields_to_level_zero(self) -> None:
        for defn in self.ROLES:
            self.upsert(defn)
        self.upsert(role("hider", [grant("widget", "read")]))
        self.upsert(role("hider2", [grant("widget", "read")]))
        self.assertEqual(self.level("Widget", "custom_cost"), 0)
        self.assertEqual(self.level("Widget", "custom_note"), 0)
        self.assertEqual(self.visibility()["hider2"]["read"], {"custom_cost", "custom_note", "custom_title_text"})

    def test_a_level_held_by_a_field_the_adapter_did_not_place_is_never_granted(self) -> None:
        self.engine.add_field("Widget", "secret_rate", permlevel=1)
        for defn in self.ROLES:
            self.upsert(defn)
        self.assertNotIn(1, {lvl for (_r, _d, lvl) in self.rules(doctype="Widget") if _r.startswith(ENGINE_NAME_PREFIX)})
        self.assertEqual(self.level("Widget", "secret_rate"), 1)
        self.assertEqual(self.visibility(), self.expected_visibility())

    def test_more_than_nine_signatures_is_refused_without_a_write(self) -> None:
        fields = [f"f{i}" for i in range(10)]
        self.add_entity("gadget", *fields)
        for i in range(9):
            self.upsert(role(f"r{i}", [grant("gadget", "read", hidden=(fields[i],))]))
        rules, setters = self.rules(), self.engine.rows("Property Setter")
        self.refused(lambda: self.upsert(role("r9", [grant("gadget", "read", hidden=("f9",))])),
                     code="limit_exceeded", reason=None)
        self.assertEqual(self.rules(), rules)
        self.assertEqual(self.engine.rows("Property Setter"), setters)


if __name__ == "__main__":
    unittest.main()
