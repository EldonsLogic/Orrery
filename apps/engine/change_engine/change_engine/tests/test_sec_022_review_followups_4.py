"""SEC-022 / BPL-032 review follow-ups 4 (ADR-0051), from Eldon's reviews of merged PR #261.

1. Case- and whitespace-insensitive Tier 0 lock (`safety_guardrails.is_locked_doctype`) shared across
   `safety_guardrails.py`, `workflow_engine.py`, `report_engine.py`, and `adapter/mapping.py` `is_protected_entity`.
2. Plan-time validation of `definition.target` on link `field.add` and `relation.*` steps.
3. Fail-closed branch for entity/field/relation steps whose pointer is not under `/entities/<id>` (e.g. `/roles/x`).
4. Refusal of `field.*` and `relation.*` steps carrying more than one parent (`unsupported_value_type`).
Synthetic data only.
"""
from __future__ import annotations

import os
import unittest
from unittest import mock

from change_engine.adapter import ChangeEngineAdapter, FrappeRuntimeBackend, FrappeSiteResolver
from change_engine.adapter import contracts_support as cs
from change_engine.adapter.mapping import is_protected_entity
from change_engine.api.endpoints import (
    FrappeDeploymentAdapter,
    apply_configuration_change,
    apply_property_setter_change,
)
from change_engine.guarded_apply import safety_guardrails
from change_engine.guarded_apply.property_setter_engine import execute_property_setter_deployment
from change_engine.guarded_apply.report_engine import (
    ReportColumn,
    ReportDefinition,
    validate_report_definition,
)
from change_engine.guarded_apply.safety_guardrails import (
    ZoneSafetyViolation,
    validate_mutation_safety,
)
from change_engine.guarded_apply.workflow_engine import (
    WorkflowDefinition,
    WorkflowStateModel,
    WorkflowTransitionModel,
    validate_workflow_state_machine,
)
from change_engine.tests.ci_engine_fake import CaseInsensitiveEngine

TENANT = "t_sec022f4"
SITE = "ci.localhost"
ULID = "01J00000000000000000000044"
_OMIT = object()

UNICODE_LOCKED_VARIANTS = (
    "GL Entry\u200b",  # zero-width space (Cf)
    "\uff27\uff2c Entry",  # full-width "ＧＬ Entry"
    "GL \u00c9ntry",  # accented Latin letter "GL Éntry"
    "GL Entr\u0443",  # Cyrillic small letter u (U+0443)
    "GL E\u0301ntry",  # combining acute accent (Mn)
    "G\u0301L Entry",  # uncomposed combining mark (Mn)
    "\ufeffGL Entry",  # BOM (Cf)
    "GL \u200cEntry",  # ZWNJ (Cf)
)

LOCKED_VARIANTS = (
    "GL Entry",
    "Gl Entry",
    "gl entry",
    "GL ENTRY",
    "GL  Entry",
    "Gl\tEntry",
    "docperm",
    "user",
    "account",
    "Account ",
    " Account",
    "ver\u017fion",  # Latin small letter long s -> casefolds to "version"
) + UNICODE_LOCKED_VARIANTS
ALLOWED_DOCTYPES = ("Customer", "Sales Invoice", "Item", "Delivery Note", "Payment Entry", "Accounts")


def _ctx(**over: object) -> dict:
    ctx = {
        "contractVersion": "0.1.2",
        "requestId": ULID,
        "correlationId": "corr_sec022_f4",
        "tenantId": TENANT,
        "caller": {"service": "control_plane", "onBehalfOf": {"kind": "user", "id": "usr_owner"}},
        "deadlineMs": 120000,
    }
    ctx.update(over)
    return ctx


def _artifact(
    steps: list[dict],
    *,
    base: dict | None = None,
    target: dict | None = None,
    inverse: dict | None = None,
) -> dict:
    counts = dict.fromkeys(("cosmetic", "config", "data_shape", "destructive", "compliance", "access", "branding"), 0)
    for s in steps:
        counts[s["impact"]] += 1
    art = {
        "artifactSchema": "0.1.0",
        "kind": "forward",
        "compiler": {"name": "bpl-compiler", "version": "0.1.0"},
        "blueprint": {
            "id": "bp-f4",
            "base": base,
            "target": target or {"hash": "sha256:" + "5" * 64, "revision": 1},
            "diffHash": ("sha256:" + "7" * 64) if base else None,
        },
        "engineTarget": {"adapter": "frappe", "versionSet": "set-example"},
        "components": [],
        "steps": steps,
        "skippedOps": [],
        "postConditions": [],
        "risk": {
            "counts": counts,
            "total": len(steps),
            "maxImpact": "data_shape",
            "needsDdlPlanGate": True,
            "touchesCompliance": False,
            "touchesAccess": counts["access"] > 0,
            "touchesLedgerOrTax": False,
            "requiresTeamReview": False,
            "irreversibleSteps": 0,
        },
        "inverse": inverse,
    }
    digest, art_id = cs.artifact_hashes(art)
    art.update(
        artifactId=art_id,
        integrity={"algorithm": "sha256-canonical-json-v1", "contentHash": digest, "signature": None},
    )
    return art


def _inverse_for(base: dict, target: dict, steps: list[dict]) -> dict:
    counts = dict.fromkeys(("cosmetic", "config", "data_shape", "destructive", "compliance", "access", "branding"), 0)
    for s in steps:
        counts[s["impact"]] += 1
    inv = {
        "artifactSchema": "0.1.0",
        "kind": "inverse",
        "compiler": {"name": "bpl-compiler", "version": "0.1.0"},
        "blueprint": {"id": "bp-f4", "base": target, "target": base, "diffHash": "sha256:" + "8" * 64},
        "engineTarget": {"adapter": "frappe", "versionSet": "set-example"},
        "components": [],
        "steps": steps,
        "skippedOps": [],
        "postConditions": [],
        "risk": {
            "counts": counts,
            "total": len(steps),
            "maxImpact": "destructive",
            "needsDdlPlanGate": False,
            "touchesCompliance": False,
            "touchesAccess": False,
            "touchesLedgerOrTax": False,
            "requiresTeamReview": False,
            "irreversibleSteps": 0,
        },
        "inverse": None,
    }
    digest, art_id = cs.artifact_hashes(inv)
    inv.update(
        artifactId=art_id,
        integrity={"algorithm": "sha256-canonical-json-v1", "contentHash": digest, "signature": None},
    )
    return inv


def _entity(
    seq: int,
    eid: str,
    *,
    pointer: str | None = None,
    fields: list[dict] | None = None,
    relations: list[dict] | None = None,
) -> dict:
    ptr = f"/entities/{eid}" if pointer is None else pointer
    return {
        "seq": seq,
        "phase": 4,
        "kind": "entity.add",
        "subject": {"kind": "entity", "id": eid, "parents": []},
        "pointer": ptr,
        "impact": "data_shape",
        "ddlImpact": "additive",
        "reversible": True,
        "params": {
            "definition": {
                "id": eid,
                "labels": {"en": eid, "ar": eid},
                "fields": [] if fields is None else fields,
                "relations": [] if relations is None else relations,
            }
        },
        "sourceOps": [ptr],
    }


def _field_step(
    seq: int,
    pointer_entity: str,
    fid: str,
    *,
    kind: str = "field.add",
    field_type: str = "string",
    target: object = _OMIT,
    parents: list[dict] | None = None,
    pointer: str | None = None,
) -> dict:
    ps = [{"kind": "entity", "id": pointer_entity}] if parents is None else parents
    if pointer is None:
        pointer = f"/entities/{pointer_entity}/fields" if kind == "field.reorder" else f"/entities/{pointer_entity}/fields/{fid}"
    if kind == "field.add":
        phase, impact, ddl = 5, "data_shape", "additive"
        defn: dict = {"id": fid, "type": field_type, "labels": {"en": fid, "ar": fid}}
        if target is not _OMIT:
            defn["target"] = target
        params: dict = {"definition": defn}
    elif kind == "field.set_property":
        phase, impact, ddl = 6, "cosmetic", "none"
        params = {"property": "/readOnly", "before": False, "after": True}
    elif kind == "field.reorder":
        phase, impact, ddl = 6, "cosmetic", "none"
        params = {"order": [fid], "previousOrder": [fid]}
    else:  # field.quarantine
        phase, impact, ddl = 15, "destructive", "none"
        params = {"definition": {"id": fid, "type": field_type, "labels": {"en": fid, "ar": fid}}}
    return {
        "seq": seq,
        "phase": phase,
        "kind": kind,
        "subject": {"kind": "field", "id": fid, "parents": ps},
        "pointer": pointer,
        "impact": impact,
        "ddlImpact": ddl,
        "reversible": True,
        "params": params,
        "sourceOps": [pointer],
    }


def _relation_step(
    seq: int,
    pointer_entity: str,
    rid: str,
    *,
    kind: str = "relation.add",
    target: object = "item",
    parents: list[dict] | None = None,
    pointer: str | None = None,
    params_override: dict | None = None,
) -> dict:
    ps = [{"kind": "entity", "id": pointer_entity}] if parents is None else parents
    ptr = f"/entities/{pointer_entity}/relations/{rid}" if pointer is None else pointer
    if kind == "relation.add":
        phase, impact, ddl = 5, "data_shape", "additive"
        defn: dict = {"id": rid, "kind": "many_to_one", "labels": {"en": rid, "ar": rid}}
        if target is not _OMIT:
            defn["target"] = target
        params: dict = {"definition": defn}
    elif kind == "relation.set_property":
        phase, impact, ddl = 6, "cosmetic", "none"
        params = {"property": "/labels/en", "before": rid, "after": rid + "2"}
    else:  # relation.quarantine
        phase, impact, ddl = 15, "destructive", "none"
        defn = {"id": rid, "kind": "many_to_one", "labels": {"en": rid, "ar": rid}}
        if target is not _OMIT:
            defn["target"] = target
        params = {"definition": defn}
    if params_override is not None:
        params = params_override
    return {
        "seq": seq,
        "phase": phase,
        "kind": kind,
        "subject": {"kind": "relation", "id": rid, "parents": ps},
        "pointer": ptr,
        "impact": impact,
        "ddlImpact": ddl,
        "reversible": True,
        "params": params,
        "sourceOps": [ptr],
    }


def _workflow_def(doctype: str) -> WorkflowDefinition:
    return WorkflowDefinition(
        workflow_name=f"{doctype} Approval",
        document_type=doctype,
        states=[
            WorkflowStateModel(state="Draft", doc_status=0, allow_edit="Sales User"),
            WorkflowStateModel(state="Approved", doc_status=1, allow_edit="Sales Manager"),
        ],
        transitions=[
            WorkflowTransitionModel(state="Draft", action="Approve", next_state="Approved", allowed="Sales Manager"),
        ],
    )


def _report_def(doctype: str) -> ReportDefinition:
    return ReportDefinition(
        report_name=f"{doctype} Summary",
        ref_doctype=doctype,
        columns=[ReportColumn(fieldname="name", label="Name", fieldtype="Data")],
    )


class TestSharedLockedDoctypeHelper(unittest.TestCase):
    """Item 1: shared `is_locked_doctype` is case- and whitespace-insensitive and fails closed on non-strings."""

    def test_helper_refuses_all_case_and_whitespace_variants_and_non_strings(self) -> None:
        for dt in LOCKED_VARIANTS:
            with self.subTest(doctype=dt):
                self.assertTrue(safety_guardrails.is_locked_doctype(dt))
        for bad in (None, 123, ["Customer"], {"doctype": "Customer"}, True):
            with self.subTest(non_string=bad):
                self.assertTrue(safety_guardrails.is_locked_doctype(bad))

    def test_helper_allows_ordinary_doctypes(self) -> None:
        for dt in ALLOWED_DOCTYPES:
            with self.subTest(doctype=dt):
                self.assertFalse(safety_guardrails.is_locked_doctype(dt))

    def test_validate_mutation_safety_refuses_locked_variants_and_allows_ordinary(self) -> None:
        for dt in LOCKED_VARIANTS:
            with self.subTest(doctype=dt):
                with self.assertRaises(ZoneSafetyViolation) as ctx:
                    validate_mutation_safety({
                        "intent": "add_custom_fields",
                        "target_doctype": dt,
                        "user_roles": ["System Manager"],
                        "changes": [{"fieldname": "custom_probe", "fieldtype": "Data", "label": "Probe"}],
                    })
                self.assertIn("Zone 2 Compliance Lock Violation", str(ctx.exception))

        for bad in (None, 123):
            with self.subTest(non_string=bad), self.assertRaises(ZoneSafetyViolation):
                validate_mutation_safety({
                    "intent": "add_custom_fields",
                    "target_doctype": bad,
                    "user_roles": ["System Manager"],
                    "changes": [{"fieldname": "custom_probe", "fieldtype": "Data", "label": "Probe"}],
                })

        for dt in ALLOWED_DOCTYPES:
            with self.subTest(allowed=dt):
                res = validate_mutation_safety({
                    "intent": "add_custom_fields",
                    "target_doctype": dt,
                    "user_roles": ["System Manager"],
                    "changes": [{"fieldname": "custom_probe", "fieldtype": "Data", "label": "Probe"}],
                })
                self.assertEqual(res["status"], "approved")

    def test_workflow_engine_refuses_locked_variants_and_allows_ordinary(self) -> None:
        extra_variants = ("Stock Ledger Entry", "stock ledger entry", "Stock  Ledger Entry ", "doctype", "custom field ")
        for dt in LOCKED_VARIANTS + extra_variants:
            with self.subTest(doctype=dt):
                res = validate_workflow_state_machine(_workflow_def(dt))
                self.assertFalse(res.is_valid, f"expected refusal for {dt!r}")
                self.assertTrue(any("Tier 0" in e for e in res.errors), res.errors)

        for dt in ALLOWED_DOCTYPES:
            with self.subTest(allowed=dt):
                res = validate_workflow_state_machine(_workflow_def(dt))
                self.assertTrue(res.is_valid, f"unexpected refusal for {dt!r}: {res.errors}")

    def test_report_engine_refuses_locked_variants_and_allows_ordinary(self) -> None:
        extra_variants = ("doctype", "custom  field ", "workflow ")
        for dt in LOCKED_VARIANTS + extra_variants:
            with self.subTest(doctype=dt):
                res = validate_report_definition(_report_def(dt))
                self.assertFalse(res.is_valid, f"expected refusal for {dt!r}")
                self.assertTrue(any("prohibited" in e.lower() for e in res.errors), res.errors)

        for dt in ALLOWED_DOCTYPES:
            with self.subTest(allowed=dt):
                res = validate_report_definition(_report_def(dt))
                self.assertTrue(res.is_valid, f"unexpected refusal for {dt!r}: {res.errors}")

    def test_is_protected_entity_reuses_locked_doctype_without_behaviour_change(self) -> None:
        for eid in (
            "gl_entry", "GL Entry", "gl_entry ", "GL  Entry", "docperm", "user", "account", "Account ",
            "sales_taxes_and_charges", "ver\u017fion", "general_ledger",
        ):
            with self.subTest(protected=eid):
                self.assertTrue(is_protected_entity(eid))
        for eid in ("customer", "sales_invoice", "item", "delivery_note", "widget"):
            with self.subTest(unprotected=eid):
                self.assertFalse(is_protected_entity(eid))


class _AdapterPlanBase(unittest.TestCase):
    def setUp(self) -> None:
        env = mock.patch.dict(os.environ, {"CHANGE_ENGINE_ENV": "test"})
        env.start()
        self.addCleanup(env.stop)

    def _adapters(self):
        engine = CaseInsensitiveEngine(SITE)
        backend = FrappeRuntimeBackend(
            site_resolver=FrappeSiteResolver(site_map={TENANT: SITE}),
            frappe_factory=lambda: engine,
            offline_ddl_simulator=True,
        )
        yield "in_memory", ChangeEngineAdapter(test_hooks=False, environment="test")
        yield "offline_engine", ChangeEngineAdapter(test_hooks=False, environment="test", frappe_backend=backend)

    def _seed_customer(self, adapter: ChangeEngineAdapter, key: str) -> dict:
        prov = adapter.call("provision_site", _ctx(), {
            "idempotencyKey": key,
            "engineTarget": {"adapter": "frappe", "versionSet": "set-example"},
            "blueprintId": "bp-f4",
            "siteClass": "sandbox",
            "countryPack": "sa",
        })
        self.assertTrue(prov["ok"], prov)
        rev1 = {"hash": "sha256:" + "5" * 64, "revision": 1}
        art1 = _artifact([_entity(1, "customer")], target=rev1)
        pl = adapter.call("plan", _ctx(), {"artifact": art1})
        self.assertTrue(pl["ok"] and pl["result"]["verdict"] == "auto_approved", pl)
        ap = adapter.call("apply", _ctx(), {
            "idempotencyKey": key + "_apply",
            "planToken": pl["result"]["planToken"],
            "artifact": art1,
            "approvals": {"changeApproved": "01J00000000000000000000010"},
        })
        self.assertTrue(ap["ok"] and ap["result"]["status"] == "applied", ap)
        return rev1

    def _plan_on_customer(self, adapter: ChangeEngineAdapter, steps: list[dict], key: str) -> dict:
        rev1 = self._seed_customer(adapter, key)
        rev2 = {"hash": "sha256:" + "6" * 64, "revision": 2}
        inv = _inverse_for(rev1, rev2, [_field_step(1, "customer", "note", kind="field.quarantine")])
        art2 = _artifact(steps, base=rev1, target=rev2, inverse=inv)
        planned = adapter.call("plan", _ctx(), {"artifact": art2})
        self.assertTrue(planned["ok"], planned)
        return planned["result"]


class TestLinkTargetsCheckedAtPlan(_AdapterPlanBase):
    """Item 2: `definition.target` on link `field.add` and on `relation.*` steps is validated at plan time."""

    BAD_TARGETS = (
        ("user", "protected_subject"),
        ("gl_entry", "protected_subject"),
        ("gl_entry ", "unsupported_value_type"),
        ("widget\n", "unsupported_value_type"),
        ("GL Entry", "unsupported_value_type"),
        (_OMIT, "unsupported_value_type"),
        (None, "unsupported_value_type"),
        (123, "unsupported_value_type"),
    )

    def test_link_field_add_targets_refused_on_both_backends(self) -> None:
        for target, expected_reason in self.BAD_TARGETS:
            step = _field_step(1, "customer", "ref_link", kind="field.add", field_type="link", target=target)
            seen = {}
            for name, adapter in self._adapters():
                with self.subTest(target=target, adapter=name):
                    result = self._plan_on_customer(adapter, [step], f"idemp_f4_lnk_{abs(hash((repr(target), name)))}")
                    got = (result["steps"][0]["disposition"], result["steps"][0].get("reasonCode"), result["verdict"])
                    seen[name] = got
                    self.assertEqual(got, ("blocked", expected_reason, "rejected"), result)
            self.assertEqual(seen["in_memory"], seen["offline_engine"])

    def test_relation_add_targets_refused_on_both_backends(self) -> None:
        for target, expected_reason in self.BAD_TARGETS:
            step = _relation_step(1, "customer", "rel_ref", kind="relation.add", target=target)
            seen = {}
            for name, adapter in self._adapters():
                with self.subTest(target=target, adapter=name):
                    result = self._plan_on_customer(adapter, [step], f"idemp_f4_rel_{abs(hash((repr(target), name)))}")
                    got = (result["steps"][0]["disposition"], result["steps"][0].get("reasonCode"), result["verdict"])
                    seen[name] = got
                    self.assertEqual(got, ("blocked", expected_reason, "rejected"), result)
            self.assertEqual(seen["in_memory"], seen["offline_engine"])

    def test_relation_quarantine_with_bad_definition_target_refused(self) -> None:
        for target, expected_reason in (
            ("user", "protected_subject"),
            ("gl_entry", "protected_subject"),
            ("gl_entry ", "unsupported_value_type"),
            ("widget\n", "unsupported_value_type"),
        ):
            params = {"definition": {"id": "rel_ref", "target": target, "kind": "many_to_one"}}
            step = _relation_step(1, "customer", "rel_ref", kind="relation.quarantine", params_override=params)
            for name, adapter in self._adapters():
                with self.subTest(target=target, adapter=name):
                    result = self._plan_on_customer(
                        adapter, [step], f"idemp_f4_relquar_{abs(hash((target, name)))}"
                    )
                    self.assertEqual(
                        (result["steps"][0]["disposition"], result["steps"][0].get("reasonCode"), result["verdict"]),
                        ("blocked", expected_reason, "rejected"),
                        result,
                    )

    def test_set_property_target_refused_on_field_and_relation(self) -> None:
        for target, expected_reason in (
            ("user", "protected_subject"),
            ("gl_entry", "protected_subject"),
            ("gl_entry ", "unsupported_value_type"),
            ("widget\n", "unsupported_value_type"),
        ):
            steps = (
                (
                    "field_set_target",
                    {
                        **_field_step(1, "customer", "ref_link", kind="field.set_property"),
                        "params": {"property": "/target", "before": "item", "after": target},
                    },
                ),
                (
                    "relation_set_target",
                    _relation_step(
                        1,
                        "customer",
                        "rel_ref",
                        kind="relation.set_property",
                        params_override={"property": "/target", "before": "item", "after": target},
                    ),
                ),
            )
            for label, step in steps:
                for name, adapter in self._adapters():
                    with self.subTest(case=label, target=target, adapter=name):
                        result = self._plan_on_customer(
                            adapter, [step], f"idemp_f4_settarget_{label}_{abs(hash((target, name)))}"
                        )
                        self.assertEqual(
                            (result["steps"][0]["disposition"], result["steps"][0].get("reasonCode"), result["verdict"]),
                            ("blocked", expected_reason, "rejected"),
                            result,
                        )

    def test_valid_link_and_relation_targets_plan_ok(self) -> None:
        controls = (
            ("link_item", _field_step(1, "customer", "ref_item", field_type="link", target="item")),
            ("link_customer", _field_step(1, "customer", "ref_cust", field_type="link", target="customer")),
            ("string_no_target", _field_step(1, "customer", "plain_note", field_type="string")),
            ("relation_item", _relation_step(1, "customer", "rel_item", kind="relation.add", target="item")),
        )
        for label, step in controls:
            for name, adapter in self._adapters():
                with self.subTest(case=label, adapter=name):
                    result = self._plan_on_customer(adapter, [step], f"idemp_f4_ok_{label}_{name}")
                    self.assertEqual(result["steps"][0]["disposition"], "ok", result)
                    self.assertEqual(result["verdict"], "auto_approved", result)


class TestNonEntityPointerFailClosed(_AdapterPlanBase):
    """Item 3: entity.add, field.* and relation.* steps whose pointer is not under `/entities/<id>` fail closed."""

    def test_pointer_under_roles_refused_with_unsupported_value_type(self) -> None:
        cases = (
            ("entity_add", _entity(1, "widget", pointer="/roles/x")),
            ("field_add", _field_step(1, "customer", "note", kind="field.add", pointer="/roles/x")),
            ("field_set_property", _field_step(1, "customer", "note", kind="field.set_property", pointer="/roles/x")),
            ("relation_add", _relation_step(1, "customer", "rel_a", kind="relation.add", pointer="/roles/x")),
            ("relation_quarantine", _relation_step(1, "customer", "rel_a", kind="relation.quarantine", pointer="/roles/x")),
        )
        for label, step in cases:
            seen = {}
            for name, adapter in self._adapters():
                with self.subTest(case=label, adapter=name):
                    result = self._plan_on_customer(adapter, [step], f"idemp_f4_ptr_{label}_{name}")
                    got = (result["steps"][0]["disposition"], result["steps"][0].get("reasonCode"), result["verdict"])
                    seen[name] = got
                    self.assertEqual(got, ("blocked", "unsupported_value_type", "rejected"), result)
            self.assertEqual(seen["in_memory"], seen["offline_engine"])


class TestExtraParentsRefused(_AdapterPlanBase):
    """Item 4: field.* and relation.* steps with more than one parent are refused with `unsupported_value_type`."""

    EXTRA_PARENTS = (
        ("second_parent_protected", [{"kind": "entity", "id": "customer"}, {"kind": "entity", "id": "user"}]),
        ("second_parent_ordinary", [{"kind": "entity", "id": "customer"}, {"kind": "entity", "id": "item"}]),
    )

    def test_field_and_relation_steps_with_extra_parents_refused_on_both_backends(self) -> None:
        for p_label, parents in self.EXTRA_PARENTS:
            steps = (
                ("field_add", _field_step(1, "customer", "note", kind="field.add", parents=parents)),
                ("field_set_property", _field_step(1, "customer", "note", kind="field.set_property", parents=parents)),
                ("field_quarantine", _field_step(1, "customer", "note", kind="field.quarantine", parents=parents)),
                ("field_reorder", _field_step(1, "customer", "note", kind="field.reorder", parents=parents)),
                ("relation_add", _relation_step(1, "customer", "rel_a", kind="relation.add", parents=parents)),
                ("relation_set_property", _relation_step(1, "customer", "rel_a", kind="relation.set_property", parents=parents)),
                ("relation_quarantine", _relation_step(1, "customer", "rel_a", kind="relation.quarantine", parents=parents)),
            )
            for s_label, step in steps:
                seen = {}
                for name, adapter in self._adapters():
                    with self.subTest(parents=p_label, step=s_label, adapter=name):
                        result = self._plan_on_customer(adapter, [step], f"idemp_f4_ep_{p_label}_{s_label}_{name}")
                        got = (result["steps"][0]["disposition"], result["steps"][0].get("reasonCode"), result["verdict"])
                        seen[name] = got
                        self.assertEqual(got, ("blocked", "unsupported_value_type", "rejected"), result)
                self.assertEqual(seen["in_memory"], seen["offline_engine"])

    def test_refusals_write_nothing_to_engine(self) -> None:
        cases = (
            ("link_user", _field_step(1, "customer", "ref_u", field_type="link", target="user")),
            ("rel_gl_ws", _relation_step(1, "customer", "rel_g", target="gl_entry ")),
            ("bad_ptr", _field_step(1, "customer", "note", pointer="/roles/x")),
            (
                "extra_parent",
                _field_step(1, "customer", "note", parents=[{"kind": "entity", "id": "customer"}, {"kind": "entity", "id": "user"}]),
            ),
        )
        for label, step in cases:
            engine = CaseInsensitiveEngine(SITE)
            backend = FrappeRuntimeBackend(
                site_resolver=FrappeSiteResolver(site_map={TENANT: SITE}),
                frappe_factory=lambda e=engine: e,
                offline_ddl_simulator=True,
            )
            adapter = ChangeEngineAdapter(test_hooks=False, environment="test", frappe_backend=backend)
            rev1 = self._seed_customer(adapter, f"idemp_f4_nw_{label}")
            before = repr(engine.ensure_site(SITE).rows)
            rev2 = {"hash": "sha256:" + "6" * 64, "revision": 2}
            inv = _inverse_for(rev1, rev2, [_field_step(1, "customer", "note", kind="field.quarantine")])
            art2 = _artifact([step], base=rev1, target=rev2, inverse=inv)
            with self.subTest(case=label):
                planned = adapter.call("plan", _ctx(), {"artifact": art2})
                self.assertTrue(planned["ok"], planned)
                self.assertEqual(planned["result"]["verdict"], "rejected", planned)
                self.assertEqual(repr(engine.ensure_site(SITE).rows), before)


class TestRestrictedLinkTargetSite(unittest.TestCase):
    """Pins safety_guardrails restricted-link check and direct-path property_setter_engine options rule."""

    RESTRICTED_LINK_VARIANTS = (
        "GL Entry",
        "gl entry",
        " Gl  Entry",
        "GL\tEntry",
        "Payment Ledger Entry",
        "payment  ledger entry ",
        "Change Engine Audit Log",
        "change engine audit log",
    ) + UNICODE_LOCKED_VARIANTS

    def setUp(self) -> None:
        FrappeDeploymentAdapter.reset_in_memory_state()

    def tearDown(self) -> None:
        FrappeDeploymentAdapter.reset_in_memory_state()

    def test_add_custom_fields_restricted_link_variants_refused(self) -> None:
        for opt in self.RESTRICTED_LINK_VARIANTS:
            with self.subTest(options=opt):
                with self.assertRaises(ZoneSafetyViolation) as ctx:
                    validate_mutation_safety({
                        "intent": "add_custom_fields",
                        "target_doctype": "Customer",
                        "user_roles": ["System Manager"],
                        "changes": [
                            {
                                "fieldname": "custom_ref_probe",
                                "fieldtype": "Link",
                                "label": "Ref Probe",
                                "options": opt,
                            }
                        ],
                    })
                self.assertIn("Restricted Link Target", str(ctx.exception))

        for bad in (None, "", "   ", 123):
            with self.subTest(invalid_options=bad):
                with self.assertRaises(ZoneSafetyViolation) as ctx:
                    validate_mutation_safety({
                        "intent": "add_custom_fields",
                        "target_doctype": "Customer",
                        "user_roles": ["System Manager"],
                        "changes": [
                            {
                                "fieldname": "custom_ref_probe",
                                "fieldtype": "Link",
                                "label": "Ref Probe",
                                "options": bad,
                            }
                        ],
                    })
                self.assertIn("Invalid Link Target", str(ctx.exception))

        for allowed in ("Customer", "Item", "User"):
            with self.subTest(allowed=allowed):
                res = validate_mutation_safety({
                    "intent": "add_custom_fields",
                    "target_doctype": "Customer",
                    "user_roles": ["System Manager"],
                    "changes": [
                        {
                            "fieldname": "custom_ref_probe",
                            "fieldtype": "Link",
                            "label": "Ref Probe",
                            "options": allowed,
                        }
                    ],
                })
                self.assertEqual(res["status"], "approved")

    def _direct_adapters(self):
        FrappeDeploymentAdapter.reset_in_memory_state()
        in_mem = FrappeDeploymentAdapter()
        yield "in_memory", in_mem, None

        engine = CaseInsensitiveEngine(SITE)
        sim = FrappeDeploymentAdapter(frappe_module=engine, offline_ddl_simulator=True)
        yield "simulated_engine", sim, engine

    def test_direct_property_setter_options_refuses_restricted_link_and_allows_select(self) -> None:
        for mode, dep, _engine in self._direct_adapters():
            # Seed one Link field and one Select field on Customer.
            link_cf = apply_configuration_change(
                doctype="Customer",
                deployment_id=f"dep_cf_link_{mode}",
                field_def={
                    "fieldname": "custom_ref_link",
                    "label": "Ref Link",
                    "fieldtype": "Link",
                    "options": "Item",
                },
                adapter=dep,
                user_roles=["System Manager"],
            )
            self.assertTrue(link_cf["success"], (mode, link_cf))
            sel_cf = apply_configuration_change(
                doctype="Customer",
                deployment_id=f"dep_cf_sel_{mode}",
                field_def={
                    "fieldname": "custom_tier",
                    "label": "Tier",
                    "fieldtype": "Select",
                    "options": "Gold\nSilver",
                },
                adapter=dep,
                user_roles=["System Manager"],
            )
            self.assertTrue(sel_cf["success"], (mode, sel_cf))

            for idx, target in enumerate(self.RESTRICTED_LINK_VARIANTS):
                with self.subTest(mode=mode, via="api", target=target):
                    res = apply_property_setter_change(
                        doctype="Customer",
                        deployment_id=f"dep_ps_bad_api_{mode}_{idx}",
                        fieldname="custom_ref_link",
                        property_name="options",
                        value=target,
                        property_type="Text",
                        user_roles=["System Manager"],
                        adapter=dep,
                    )
                    self.assertFalse(res["success"], res)
                    self.assertEqual(res["status"], "REJECTED", res)
                    self.assertEqual(res["disposition"], "ZONE_SAFETY_VIOLATION", res)
                    self.assertIn("Restricted Link Target", res["reason"])
                    self.assertIsNone(dep.get_property_setter("Customer", "custom_ref_link", "options"))

                with self.subTest(mode=mode, via="engine", target=target):
                    res = execute_property_setter_deployment(
                        db=dep,
                        deployment_id=f"dep_ps_bad_eng_{mode}_{idx}",
                        site_id=SITE,
                        doctype="Customer",
                        fieldname="custom_ref_link",
                        property_name="options",
                        value=target,
                        property_type="Text",
                        user_roles=["System Manager"],
                    )
                    self.assertFalse(res["success"], res)
                    self.assertEqual(res["status"], "REJECTED", res)
                    self.assertEqual(res["disposition"], "ZONE_SAFETY_VIOLATION", res)
                    self.assertIsNone(dep.get_property_setter("Customer", "custom_ref_link", "options"))

            # Empty options on Link field is also refused.
            with self.subTest(mode=mode, target="empty_link"):
                res_empty = apply_property_setter_change(
                    doctype="Customer",
                    deployment_id=f"dep_ps_empty_{mode}",
                    fieldname="custom_ref_link",
                    property_name="options",
                    value="",
                    property_type="Text",
                    user_roles=["System Manager"],
                    adapter=dep,
                )
                self.assertFalse(res_empty["success"], res_empty)
                self.assertEqual(res_empty["status"], "REJECTED", res_empty)
                self.assertIsNone(dep.get_property_setter("Customer", "custom_ref_link", "options"))

            # Unknown-fieldtype fail-closed: restricted targets refused even if metadata has no field entry.
            for idx, target in enumerate(("GL Entry", "gl entry", " Gl  Entry")):
                with self.subTest(mode=mode, unknown_field=True, target=target):
                    res_unk = apply_property_setter_change(
                        doctype="Customer",
                        deployment_id=f"dep_ps_unk_{mode}_{idx}",
                        fieldname="custom_unregistered_field",
                        property_name="options",
                        value=target,
                        property_type="Text",
                        user_roles=["System Manager"],
                        adapter=dep,
                    )
                    self.assertFalse(res_unk["success"], res_unk)
                    self.assertEqual(res_unk["status"], "REJECTED", res_unk)
                    self.assertIsNone(dep.get_property_setter("Customer", "custom_unregistered_field", "options"))

            # Control: ordinary Link target still applies.
            with self.subTest(mode=mode, control="link_customer"):
                res_ok = apply_property_setter_change(
                    doctype="Customer",
                    deployment_id=f"dep_ps_ok_link_{mode}",
                    fieldname="custom_ref_link",
                    property_name="options",
                    value="Customer",
                    property_type="Text",
                    user_roles=["System Manager"],
                    adapter=dep,
                )
                self.assertTrue(res_ok["success"], res_ok)
                self.assertEqual(res_ok["status"], "APPLIED", res_ok)

            # Control: Select options (ASCII and Arabic) still apply.
            for label, opts in (("ascii", "Gold\nSilver\nPlatinum"), ("arabic", "\u0630\u0647\u0628\u064a\n\u0641\u0636\u064a")):
                with self.subTest(mode=mode, control=f"select_{label}"):
                    res_sel = apply_property_setter_change(
                        doctype="Customer",
                        deployment_id=f"dep_ps_ok_sel_{mode}_{label}",
                        fieldname="custom_tier",
                        property_name="options",
                        value=opts,
                        property_type="Text",
                        user_roles=["System Manager"],
                        adapter=dep,
                    )
                    self.assertTrue(res_sel["success"], res_sel)
                    self.assertEqual(res_sel["status"], "APPLIED", res_sel)
                    ps = dep.get_property_setter("Customer", "custom_tier", "options")
                    self.assertIsNotNone(ps)
                    self.assertEqual(ps["value"], opts)


class TestPlanOptionsOnLinkAndRelation(_AdapterPlanBase):
    """Review fix round item 1: `/options` on link fields, relations, and unproven fields is refused at plan time."""

    def _seed_customer_with_fields(self, adapter: ChangeEngineAdapter, key: str) -> dict:
        rev1 = self._seed_customer(adapter, key)
        rev2 = {"hash": "sha256:" + "a" * 64, "revision": 2}
        select_step = _field_step(2, "customer", "tier", kind="field.add", field_type="select")
        select_step["params"]["definition"]["options"] = [
            {"value": "gold", "labels": {"en": "Gold", "ar": "\u0630\u0647\u0628\u064a"}},
        ]
        steps = [
            _field_step(1, "customer", "ref_link", kind="field.add", field_type="link", target="item"),
            select_step,
            _relation_step(3, "customer", "rel_item", kind="relation.add", target="item"),
        ]
        inv = _inverse_for(
            rev1,
            rev2,
            [
                _field_step(1, "customer", "ref_link", kind="field.quarantine"),
                _field_step(2, "customer", "tier", kind="field.quarantine"),
                _relation_step(3, "customer", "rel_item", kind="relation.quarantine"),
            ],
        )
        art2 = _artifact(steps, base=rev1, target=rev2, inverse=inv)
        pl = adapter.call("plan", _ctx(), {"artifact": art2})
        self.assertTrue(pl["ok"] and pl["result"]["verdict"] == "auto_approved", pl)
        ap = adapter.call("apply", _ctx(), {
            "idempotencyKey": key + "_apply_fields",
            "planToken": pl["result"]["planToken"],
            "artifact": art2,
            "approvals": {"changeApproved": "01J00000000000000000000011"},
        })
        self.assertTrue(ap["ok"] and ap["result"]["status"] == "applied", ap)
        return rev2

    def test_reviewer_repro_link_options_gl_entry_refused_on_both_adapters_with_zero_writes(self) -> None:
        step = {
            **_field_step(1, "customer", "ref_link", kind="field.set_property"),
            "params": {"property": "/options", "before": "Item", "after": "GL Entry"},
        }
        seen = {}
        for name, adapter in self._adapters():
            with self.subTest(adapter=name):
                rev2 = self._seed_customer_with_fields(adapter, f"idemp_repro_{name}")
                engine = adapter.frappe_backend._frappe_factory() if adapter.frappe_backend else None
                before_rows = repr(engine.ensure_site(SITE).rows) if engine else None
                rev3 = {"hash": "sha256:" + "b" * 64, "revision": 3}
                inv = _inverse_for(rev2, rev3, [_field_step(1, "customer", "ref_link", kind="field.set_property")])
                art3 = _artifact([step], base=rev2, target=rev3, inverse=inv)
                planned = adapter.call("plan", _ctx(), {"artifact": art3})
                self.assertTrue(planned["ok"], planned)
                res = planned["result"]
                got = (res["steps"][0]["disposition"], res["steps"][0].get("reasonCode"), res["verdict"])
                seen[name] = got
                self.assertEqual(got, ("blocked", "protected_subject", "rejected"), res)
                ap = adapter.call("apply", _ctx(), {
                    "idempotencyKey": f"idemp_repro_apply_{name}",
                    "planToken": res["planToken"],
                    "artifact": art3,
                    "approvals": {"changeApproved": "01J00000000000000000000012"},
                })
                self.assertTrue(ap["ok"], ap)
                self.assertEqual(ap["result"]["status"], "rejected", ap)
                if engine is not None:
                    self.assertEqual(repr(engine.ensure_site(SITE).rows), before_rows)
                    ps_rows = engine.rows("Property Setter")
                    self.assertFalse(
                        any(r.get("field_name") == "custom_ref_link" and r.get("property") == "options" for r in ps_rows),
                        ps_rows,
                    )
        self.assertEqual(seen["in_memory"], seen["offline_engine"])

    def test_link_and_relation_options_refused_for_all_values_and_select_allowed(self) -> None:
        bad_options = (
            ("GL Entry", "protected_subject"),
            ("User", "protected_subject"),
            ("gl_entry", "protected_subject"),
            ("user", "protected_subject"),
            ("gl entry", "protected_subject"),
            (["GL Entry"], "protected_subject"),
            ([{"value": "GL Entry"}], "protected_subject"),
            ("GL Entry\u200b", "protected_subject"),
            ("\uff27\uff2c Entry", "protected_subject"),
            ("GL \u00c9ntry", "protected_subject"),
            ("GL Entr\u0443", "protected_subject"),
            ("Item", "unsupported_value_type"),
            ("item", "unsupported_value_type"),
            ("Server Script", "unsupported_value_type"),
            (None, "unsupported_value_type"),
            (_OMIT, "unsupported_value_type"),
        )
        for idx, (after_val, expected_reason) in enumerate(bad_options):
            params: dict = {"property": "/options", "before": "Item"}
            if after_val is not _OMIT:
                params["after"] = after_val
            steps_by_kind = (
                ("field_link", {**_field_step(1, "customer", "ref_link", kind="field.set_property"), "params": params}),
                (
                    "relation",
                    _relation_step(1, "customer", "rel_item", kind="relation.set_property", params_override=params),
                ),
            )
            for label, step in steps_by_kind:
                seen = {}
                for name, adapter in self._adapters():
                    with self.subTest(case=label, after=after_val, adapter=name):
                        rev2 = self._seed_customer_with_fields(adapter, f"idemp_opt_{label}_{idx}_{name}")
                        rev3 = {"hash": "sha256:" + "c" * 64, "revision": 3}
                        inv = _inverse_for(rev2, rev3, [_field_step(1, "customer", "ref_link", kind="field.set_property")])
                        art3 = _artifact([step], base=rev2, target=rev3, inverse=inv)
                        planned = adapter.call("plan", _ctx(), {"artifact": art3})
                        self.assertTrue(planned["ok"], planned)
                        res = planned["result"]
                        got = (res["steps"][0]["disposition"], res["steps"][0].get("reasonCode"), res["verdict"])
                        seen[name] = got
                        self.assertEqual(got, ("blocked", expected_reason, "rejected"), res)
                self.assertEqual(seen["in_memory"], seen["offline_engine"])

        # Unknown / missing field cannot be proven non-link -> refused on /options.
        unk_step = {
            **_field_step(1, "customer", "unknown_fld", kind="field.set_property"),
            "params": {"property": "/options", "before": "Item", "after": "Customer"},
        }
        for name, adapter in self._adapters():
            with self.subTest(case="unknown_field", adapter=name):
                res = self._plan_on_customer(adapter, [unk_step], f"idemp_opt_unk_{name}")
                self.assertEqual(
                    (res["steps"][0]["disposition"], res["steps"][0].get("reasonCode"), res["verdict"]),
                    ("blocked", "unsupported_value_type", "rejected"),
                    res,
                )

        # Two-step combo: changing /type to link in the same artifact prevents /options on that field.
        combo_steps = [
            {
                **_field_step(1, "customer", "tier", kind="field.set_property"),
                "params": {"property": "/type", "before": "select", "after": "link"},
            },
            {
                **_field_step(2, "customer", "tier", kind="field.set_property"),
                "params": {"property": "/options", "before": [], "after": "GL Entry"},
            },
        ]
        for name, adapter in self._adapters():
            with self.subTest(case="type_then_options_combo", adapter=name):
                rev2 = self._seed_customer_with_fields(adapter, f"idemp_opt_combo_{name}")
                rev3 = {"hash": "sha256:" + "d" * 64, "revision": 3}
                inv = _inverse_for(rev2, rev3, [_field_step(1, "customer", "tier", kind="field.set_property")])
                art3 = _artifact(combo_steps, base=rev2, target=rev3, inverse=inv)
                planned = adapter.call("plan", _ctx(), {"artifact": art3})
                self.assertTrue(planned["ok"], planned)
                res = planned["result"]
                self.assertEqual(res["verdict"], "rejected", res)
                self.assertEqual(res["steps"][1]["disposition"], "blocked", res)
                self.assertEqual(res["steps"][1].get("reasonCode"), "protected_subject", res)

        # Positive control: proven Select field `/options` still plans ok.
        sel_step = {
            **_field_step(1, "customer", "tier", kind="field.set_property"),
            "params": {
                "property": "/options",
                "before": [{"value": "gold", "labels": {"en": "Gold", "ar": "\u0630\u0647\u0628\u064a"}}],
                "after": [
                    {"value": "gold", "labels": {"en": "Gold", "ar": "\u0630\u0647\u0628\u064a"}},
                    {"value": "silver", "labels": {"en": "Silver", "ar": "\u0641\u0636\u064a"}},
                ],
            },
        }
        for name, adapter in self._adapters():
            with self.subTest(case="select_options_ok", adapter=name):
                rev2 = self._seed_customer_with_fields(adapter, f"idemp_opt_sel_ok_{name}")
                rev3 = {"hash": "sha256:" + "e" * 64, "revision": 3}
                inv = _inverse_for(rev2, rev3, [_field_step(1, "customer", "tier", kind="field.set_property")])
                art3 = _artifact([sel_step], base=rev2, target=rev3, inverse=inv)
                planned = adapter.call("plan", _ctx(), {"artifact": art3})
                self.assertTrue(planned["ok"], planned)
                self.assertEqual(planned["result"]["steps"][0]["disposition"], "ok", planned)
                self.assertEqual(planned["result"]["verdict"], "auto_approved", planned)


class TestEntityAddInlineTargets(_AdapterPlanBase):
    """Review fix round item 2: `entity.add` inline `definition.fields[]` and `relations[]` targets checked at plan."""

    BAD_INLINE = (
        ("user", "protected_subject"),
        ("gl_entry", "protected_subject"),
        ("GL Entry", "unsupported_value_type"),
        ("gl_entry ", "unsupported_value_type"),
        ("widget\n", "unsupported_value_type"),
        (_OMIT, "unsupported_value_type"),
        (None, "unsupported_value_type"),
        (123, "unsupported_value_type"),
    )

    def test_entity_add_inline_field_link_targets_refused_with_zero_writes(self) -> None:
        for idx, (target, expected_reason) in enumerate(self.BAD_INLINE):
            fld: dict = {"id": "ref_bad", "type": "link", "labels": {"en": "Ref Bad", "ar": "Ref Bad"}}
            if target is not _OMIT:
                fld["target"] = target
            step = _entity(1, "widget", fields=[fld])
            seen = {}
            for name, adapter in self._adapters():
                with self.subTest(target=target, adapter=name):
                    engine = adapter.frappe_backend._frappe_factory() if adapter.frappe_backend else None
                    rev1 = self._seed_customer(adapter, f"idemp_ent_fld_{idx}_{name}")
                    before_rows = repr(engine.ensure_site(SITE).rows) if engine else None
                    rev2 = {"hash": "sha256:" + "6" * 64, "revision": 2}
                    inv = _inverse_for(rev1, rev2, [_entity(1, "widget")])
                    art2 = _artifact([step], base=rev1, target=rev2, inverse=inv)
                    planned = adapter.call("plan", _ctx(), {"artifact": art2})
                    self.assertTrue(planned["ok"], planned)
                    res = planned["result"]
                    got = (res["steps"][0]["disposition"], res["steps"][0].get("reasonCode"), res["verdict"])
                    seen[name] = got
                    self.assertEqual(got, ("blocked", expected_reason, "rejected"), res)
                    ap = adapter.call("apply", _ctx(), {
                        "idempotencyKey": f"idemp_ent_fld_ap_{idx}_{name}",
                        "planToken": res["planToken"],
                        "artifact": art2,
                        "approvals": {"changeApproved": "01J00000000000000000000013"},
                    })
                    self.assertTrue(ap["ok"], ap)
                    self.assertEqual(ap["result"]["status"], "rejected", ap)
                    if engine is not None:
                        self.assertEqual(repr(engine.ensure_site(SITE).rows), before_rows)
            self.assertEqual(seen["in_memory"], seen["offline_engine"])

    def test_entity_add_inline_relation_targets_refused_and_valid_inline_allowed(self) -> None:
        for idx, (target, expected_reason) in enumerate((
            ("user", "protected_subject"),
            ("gl_entry", "protected_subject"),
            ("GL Entry", "unsupported_value_type"),
            (_OMIT, "unsupported_value_type"),
        )):
            rel: dict = {"id": "rel_bad", "kind": "many_to_one", "labels": {"en": "Rel Bad", "ar": "Rel Bad"}}
            if target is not _OMIT:
                rel["target"] = target
            step = _entity(1, "widget", relations=[rel])
            for name, adapter in self._adapters():
                with self.subTest(rel_target=target, adapter=name):
                    res = self._plan_on_customer(adapter, [step], f"idemp_ent_rel_{idx}_{name}")
                    self.assertEqual(
                        (res["steps"][0]["disposition"], res["steps"][0].get("reasonCode"), res["verdict"]),
                        ("blocked", expected_reason, "rejected"),
                        res,
                    )

        # Positive control: entity.add with valid inline link field, string field, and relation plans ok.
        good = _entity(
            1,
            "widget",
            fields=[
                {"id": "ref_item", "type": "link", "target": "item", "labels": {"en": "Item", "ar": "Item"}},
                {"id": "note", "type": "string", "labels": {"en": "Note", "ar": "Note"}},
            ],
            relations=[
                {"id": "rel_cust", "target": "customer", "kind": "many_to_one", "labels": {"en": "Cust", "ar": "Cust"}},
            ],
        )
        for name, adapter in self._adapters():
            with self.subTest(control="valid_inline", adapter=name):
                res = self._plan_on_customer(adapter, [good], f"idemp_ent_ok_{name}")
                self.assertEqual(res["steps"][0]["disposition"], "ok", res)
                self.assertEqual(res["verdict"], "auto_approved", res)


if __name__ == "__main__":
    unittest.main()
