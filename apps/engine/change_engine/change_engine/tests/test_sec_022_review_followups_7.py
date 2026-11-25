"""SEC-022 / BPL-032 review follow-up 7 (ADR-0051 items 3 and 7), from Eldon's review of merged PR #274 (Medium 1, Low 2).

`entity.set_property` could change a field's type in the config without the change being recorded in the `/type`
history (`_typeChangedPointers`), and one form needed no approval gate. Rule: `entity.*` kinds address exactly
`/entities/<id>`, and `entity.set_property` may not name `id`, `fields` or `relations` (or anything under them);
`field.set_property` may touch `type` only as exactly `/type` (gated and recorded). Refused at plan time with
`unsupported_value_type`, nothing written. Valid entity-level steps still plan. Synthetic data only.
"""
from __future__ import annotations

import unittest
from unittest import mock

from change_engine.adapter import contracts_support as cs
from change_engine.adapter.engine import KIND_ROOTS, STEP_KINDS
from change_engine.tests.test_sec_022_review_followups_4 import (
    _AdapterPlanBase,
    _artifact,
    _ctx,
    _entity,
    _field_step,
    SITE,
    TENANT,
    _inverse_for,
    TestPlanOptionsOnLinkAndRelation,
    TestTypeChangeHistoryRefusesOptions,
    _relation_step,
)

_ENTITY_PHASE = {"entity.set_property": 6, "entity.quarantine": 16}


def _entity_step(kind: str, pointer: str, params: dict | None = None, *, eid: str = "customer") -> dict:
    if kind == "entity.set_property":
        params = params or {"property": "/labels/en", "before": "customer", "after": "Customer"}
        impact, ddl = "cosmetic", "none"
    else:
        params = {"definition": {"id": eid, "labels": {"en": eid, "ar": eid}, "fields": []}}
        impact, ddl = "destructive", "none"
    return {
        "seq": 1,
        "phase": _ENTITY_PHASE[kind],
        "kind": kind,
        "subject": {"kind": "entity", "id": eid, "parents": []},
        "pointer": pointer,
        "impact": impact,
        "ddlImpact": ddl,
        "reversible": True,
        "params": params,
        "sourceOps": [pointer],
    }


def _set(prop: str, after: object = "x", before: object = None) -> dict:
    return {"property": prop, "before": before, "after": after}


CUSTOMER = "/entities/customer"
LINK = CUSTOMER + "/fields/ref_link"
_SELECT_FIELD = {"id": "ref_link", "type": "select", "labels": {"en": "ref_link", "ar": "ref_link"}}


class _Base(_AdapterPlanBase):
    # customer with link field `ref_link` (-> item) and select field `tier`, applied through the real plan and apply
    _seed_with_fields = TestTypeChangeHistoryRefusesOptions._seed_customer_with_fields
    # the same customer plus relation `rel_item` (-> item), for relation.set_property steps
    _seed_with_relation = TestPlanOptionsOnLinkAndRelation._seed_customer_with_fields

    def _snapshot(self, adapter) -> tuple:
        engine = adapter.frappe_backend._frappe_factory() if adapter.frappe_backend else None
        rows = repr(engine.ensure_site(SITE).rows) if engine and hasattr(engine, "ensure_site") else None
        return adapter.call("export_config", _ctx(), {})["result"], rows

    def _plan_one(self, adapter, rev: dict, step: dict, tag: str) -> tuple[dict, dict]:
        target = {"hash": "sha256:" + "f" * 64, "revision": rev["revision"] + 1}
        inv = _inverse_for(rev, target, [_field_step(1, "customer", "tier", kind="field.quarantine")])
        art = _artifact([step], base=rev, target=target, inverse=inv)
        res = adapter.call("plan", _ctx(), {"artifact": art})
        self.assertTrue(res["ok"], res)
        return art, res["result"]

    def _refuse_all(self, steps: list[dict], tag: str, *, apply: bool = False) -> None:
        for name, adapter in self._adapters():
            rev = self._seed_with_fields(adapter, f"idemp_f7_{tag}_{name}")
            for i, step in enumerate(steps):
                with self.subTest(adapter=name, kind=step["kind"], pointer=step["pointer"], prop=step["params"].get("property")):
                    self._assert_refused(adapter, name, rev, step, f"{tag}{i}", apply=apply)

    def _assert_refused(self, adapter, name: str, rev: dict, step: dict, tag: str, *, apply: bool = False) -> None:
        before = self._snapshot(adapter)
        art, res = self._plan_one(adapter, rev, step, tag)
        got = res["steps"][0]
        self.assertEqual((got["disposition"], got.get("reasonCode")), ("blocked", "unsupported_value_type"), res)
        self.assertEqual(res["verdict"], "rejected")
        self.assertEqual(self._snapshot(adapter), before, "plan must not write")
        if apply:
            ap = adapter.call("apply", _ctx(), {
                "idempotencyKey": f"idemp_f7_ap_{tag}_{name}",
                "planToken": res["planToken"],
                "artifact": art,
                "approvals": {
                    "changeApproved": "01J00000000000000000000041",
                    "gateApproved": "01J00000000000000000000042",
                },
            })
            self.assertTrue(ap["ok"], ap)
            self.assertEqual(ap["result"]["status"], "rejected", ap)
            self.assertEqual(self._snapshot(adapter), before, "a refused plan must leave no write after apply")
        status = adapter.call("site_status", _ctx(), {})
        self.assertNotEqual(status["result"].get("state"), "recovery_required", status)
        cfg = adapter.call("export_config", _ctx(), {})["result"]
        fld = next(f for e in cfg["export"]["sections"]["entities"] if e["id"] == "customer" for f in e["fields"] if f["id"] == "ref_link")
        self.assertEqual(fld["type"], "link", "the field stays a link")


class TestReviewerRepro(_Base):
    """Eldon's two forms, starting from link field `ref_link` on `customer`, on both adapters."""

    def test_form_a_deep_pointer_type_change_refused(self) -> None:
        step = _entity_step("entity.set_property", LINK, _set("/type", "select", "link"))
        self._refuse_all([step], "a", apply=True)

    def test_form_b_fields_property_with_retyped_field_refused(self) -> None:
        retyped = [_SELECT_FIELD, {"id": "tier", "type": "select", "labels": {"en": "t", "ar": "t"}}]
        step = _entity_step("entity.set_property", CUSTOMER, _set("/fields", retyped))
        self._refuse_all([step], "b", apply=True)

    def test_options_on_the_link_stay_refused_after_the_refused_type_change(self) -> None:
        # Eldon's follow-on: `/options` = User on `ref_link` must still be refused (the field is still a link).
        for name, adapter in self._adapters():
            with self.subTest(adapter=name):
                rev = self._seed_with_fields(adapter, f"idemp_f7_chain_{name}")
                for first in (
                    _entity_step("entity.set_property", LINK, _set("/type", "select", "link")),
                    _entity_step("entity.set_property", CUSTOMER, _set("/fields", [_SELECT_FIELD])),
                ):
                    self._plan_one(adapter, rev, first, "chain")
                opt = {
                    **_field_step(1, "customer", "ref_link", kind="field.set_property"),
                    "params": {"property": "/options", "before": "Item", "after": "User"},
                }
                _, res = self._plan_one(adapter, rev, opt, "chain_opt")
                got = res["steps"][0]
                self.assertEqual((got["disposition"], got.get("reasonCode")), ("blocked", "protected_subject"), res)

    def test_reported_side_cases_refused(self) -> None:
        cases = (
            _entity_step("entity.set_property", CUSTOMER, _set("/fields/ref_link/type", "select", "link")),
            _entity_step("entity.quarantine", LINK),
        )
        self._refuse_all(list(cases), "side")


class TestEntityPointerShape(_Base):
    def test_entity_kinds_need_exactly_the_entity_pointer(self) -> None:
        steps = []
        for kind in ("entity.set_property", "entity.quarantine"):
            for ptr in (
                CUSTOMER + "/fields", LINK, LINK + "/options", CUSTOMER + "/relations/rel", CUSTOMER + "/labels",
                CUSTOMER + "/", CUSTOMER + "/x/y/z",
            ):
                steps.append(_entity_step(kind, ptr))
        for ptr in (CUSTOMER + "/fields/newf", CUSTOMER + "/fields", CUSTOMER + "/x"):
            steps.append(_entity(1, "customer", pointer=ptr))
        self._refuse_all(steps, "shape")


class TestEntityStructuralProperties(_Base):
    def test_malformed_properties_refused_by_the_engine_itself(self) -> None:
        """The contract schema refuses these first; the engine does not rely on it (validation can be skipped)."""
        props = ("/fields/", "/fields//x", "fields", "", "/", "//fields", "//", 7, None, ["/fields"])
        for name, adapter in self._adapters():
            self._seed_with_fields(adapter, f"idemp_f7_mal_{name}")
            site = adapter._need_site(adapter.store.get_site(TENANT))
            for prop in props:
                step = _entity_step("entity.set_property", CUSTOMER, {"property": prop, "before": None, "after": []})
                with self.subTest(adapter=name, prop=prop):
                    got = adapter._judge(site, step, {"customer"})
                    self.assertEqual(got[:2], ("blocked", "unsupported_value_type"))

    def test_structural_properties_refused(self) -> None:
        props = (
            "/fields", "/fields/ref_link", "/fields/ref_link/type", "/fields/0/type", "/fields/ref_link/options",
            "/relations", "/relations/rel", "/relations/rel/target", "/id", "/id/x",
        )
        self._refuse_all(
            [_entity_step("entity.set_property", CUSTOMER, {"property": p, "before": None, "after": []}) for p in props],
            "prop",
        )


class TestFieldTypeOnlyAsExactType(_Base):
    def test_deeper_type_properties_refused_on_field_set_property(self) -> None:
        steps = [
            {**_field_step(1, "customer", "ref_link", kind="field.set_property"), "params": _set(prop, "select", "link")}
            for prop in ("/type/x", "/type/0", "/type/x/y")
        ]
        self._refuse_all(steps, "ftype")

    def test_malformed_type_properties_refused_by_the_engine_itself(self) -> None:
        for name, adapter in self._adapters():
            self._seed_with_fields(adapter, f"idemp_f7_ftm_{name}")
            site = adapter._need_site(adapter.store.get_site(TENANT))
            for prop in ("/type/", "/type//x"):
                step = {**_field_step(1, "customer", "ref_link", kind="field.set_property"), "params": _set(prop, "select", "link")}
                with self.subTest(adapter=name, prop=prop):
                    self.assertEqual(adapter._judge(site, step, {"customer"})[:2], ("blocked", "unsupported_value_type"))

    def test_exact_type_change_still_gated_and_recorded(self) -> None:
        step = {**_field_step(1, "customer", "ref_link", kind="field.set_property"), "params": _set("/type", "select", "link")}
        for name, adapter in self._adapters():
            with self.subTest(adapter=name):
                rev = self._seed_with_fields(adapter, f"idemp_f7_exact_{name}")
                _, res = self._plan_one(adapter, rev, step, "exact")
                self.assertEqual(res["verdict"], "needs_gate_approval", res)
                self.assertEqual(res["steps"][0]["disposition"], "gated")


class TestValidEntityStepsStillPlan(_Base):
    def test_entity_level_properties_plan_ok_and_apply(self) -> None:
        props = (
            ("/labels", {"en": "Customer", "ar": "Customer"}),
            ("/labels/en", "Customer"),
            ("/pluralLabels", {"en": "Customers", "ar": "Customers"}),
            ("/kind", "master"),
            ("/numbering", {"prefix": "C-", "padding": 4}),
            ("/numbering/prefix", "C-"),
            ("/workflow", "wf"),
            ("/components", []),
            ("/labels/a~1b", "slash"),
        )
        for name, adapter in self._adapters():
            rev = self._seed_with_fields(adapter, f"idemp_f7_ok_{name}")
            for prop, after in props:
                step = _entity_step("entity.set_property", CUSTOMER, _set(prop, after))
                with self.subTest(adapter=name, prop=prop):
                    _, res = self._plan_one(adapter, rev, step, "ok")
                    got = res["steps"][0]
                    self.assertEqual((got["disposition"], got.get("reasonCode")), ("ok", None), res)
                    self.assertEqual(res["verdict"], "auto_approved")

    def test_entity_property_applies_and_leaves_fields_alone(self) -> None:
        for name, adapter in self._adapters():
            with self.subTest(adapter=name):
                rev = self._seed_with_fields(adapter, f"idemp_f7_apply_{name}")
                step = _entity_step("entity.set_property", CUSTOMER, _set("/numbering", {"prefix": "C-"}))
                art, res = self._plan_one(adapter, rev, step, "apply")
                ap = adapter.call("apply", _ctx(), {
                    "idempotencyKey": f"idemp_f7_apply_do_{name}",
                    "planToken": res["planToken"],
                    "artifact": art,
                    "approvals": {"changeApproved": "01J00000000000000000000043"},
                })
                self.assertTrue(ap["ok"] and ap["result"]["status"] == "applied", ap)
                cfg = adapter.call("export_config", _ctx(), {})["result"]
                cust = next(e for e in cfg["export"]["sections"]["entities"] if e["id"] == "customer")
                self.assertEqual(cust["numbering"], {"prefix": "C-"})
                self.assertEqual({f["id"]: f["type"] for f in cust["fields"]}["ref_link"], "link")

    def test_entity_add_and_quarantine_at_the_entity_pointer_still_plan(self) -> None:
        for name, adapter in self._adapters():
            with self.subTest(adapter=name):
                rev = self._seed_with_fields(adapter, f"idemp_f7_eq_{name}")
                _, res = self._plan_one(adapter, rev, _entity(1, "widget"), "add")
                self.assertEqual(res["steps"][0]["disposition"], "ok", res)
                _, res = self._plan_one(adapter, rev, _entity_step("entity.quarantine", CUSTOMER), "q")
                self.assertEqual(res["steps"][0]["disposition"], "ok", res)

    def test_bpdiff_shaped_entity_property_step_plans(self) -> None:
        """The compiler turns a diff op `/entities/<id>/<prop path>` into pointer `/entities/<id>` plus property
        `/<prop path>` (compiler `steps.py`, the settings rule); an entity label change must keep planning."""
        step = _entity_step("entity.set_property", CUSTOMER, _set("/labels/ar", "عميل", "x"))
        step["impact"] = "cosmetic"
        for name, adapter in self._adapters():
            with self.subTest(adapter=name):
                rev = self._seed_with_fields(adapter, f"idemp_f7_bpd_{name}")
                _, res = self._plan_one(adapter, rev, step, "bpd")
                self.assertEqual(res["steps"][0]["disposition"], "ok", res)


class TestKindRootsFallback(_AdapterPlanBase):
    """Low 2: a kind with no `KIND_ROOTS` entry gets no root at all."""

    def test_unmapped_kind_has_no_root(self) -> None:
        self.assertEqual(KIND_ROOTS.get("binding.add", frozenset()), frozenset())

    def test_supported_kind_without_a_mapping_is_refused_at_plan(self) -> None:
        step = {
            **_entity_step("entity.set_property", CUSTOMER),
            "kind": "binding.add",
            "phase": 5,
            "params": {"definition": {"id": "customer", "labels": {"en": "x", "ar": "x"}}},
        }
        for name, adapter in self._adapters():
            with self.subTest(adapter=name):
                rev = self._seed_customer(adapter, f"idemp_f7_fb_{name}")
                target = {"hash": "sha256:" + "f" * 64, "revision": 2}
                inv = _inverse_for(rev, target, [_field_step(1, "customer", "note", kind="field.quarantine")])
                art = _artifact([step], base=rev, target=target, inverse=inv)
                with mock.patch.dict(STEP_KINDS, {"binding.add": "supported"}):
                    res = adapter.call("plan", _ctx(), {"artifact": art})
                self.assertTrue(res["ok"], res)
                got = res["result"]["steps"][0]
                self.assertEqual((got["disposition"], got.get("reasonCode")), ("blocked", "unsupported_value_type"), res)


def _rel_step(prop: object) -> dict:
    """`relation.set_property` on relation `rel_item` of `customer`, seeded by `_seed_with_relation`."""
    return _relation_step(1, "customer", "rel_item", kind="relation.set_property", params_override=_set(prop))


class TestPropertyMustBeAPointer(_Base):
    """Cross-model review of #280: `_segs` drops the text before the first `/`, so without schema validation
    `x/type` wrote `type` on the field with no gate and no history entry, and `x/options` / `x/target` skipped
    their exact-spelling checks. Every kind that carries `params.property` now needs a well-formed pointer, and
    on fields and relations `type`, `options` and `target` only as exactly `/type`, `/options`, `/target`."""

    def test_reviewer_repro_without_schema_validation(self) -> None:
        # The pure-Python path: no schema validator, so the contract pattern is not enforced.
        steps = [
            {**_field_step(1, "customer", "ref_link", kind="field.set_property"), "params": _set(prop, "select", "link")}
            for prop in ("x/type", "type", "x/options", "/options/0", "x/target", "/target/x")
        ]
        with mock.patch.object(cs, "_validator_for", return_value=None):
            self._refuse_all(steps, "nopat", apply=True)

    def test_every_property_kind_needs_a_well_formed_pointer(self) -> None:
        bad = ("x/type", "type", "x/options", "options", "x/target", "x", "", "/", "//", "/a/", 7, None, ["/type"])
        cases = []
        for prop in bad:
            cases.append({**_field_step(1, "customer", "ref_link", kind="field.set_property"), "params": _set(prop)})
            cases.append(_rel_step(prop))
            cases.append({**_entity_step("entity.set_property", CUSTOMER), "params": _set(prop)})
            sett = {**_entity_step("entity.set_property", CUSTOMER), "params": _set(prop)}
            sett.update(kind="settings.set", phase=1, pointer="/company", subject={"kind": "settings", "id": "company", "parents": []})
            cases.append(sett)
            comp = {**_entity_step("entity.set_property", CUSTOMER), "params": _set(prop)}
            comp.update(kind="component.configure", phase=2, pointer="/components/c1", subject={"kind": "component", "id": "c1", "parents": []})
            cases.append(comp)
        for name, adapter in self._adapters():
            self._seed_with_relation(adapter, f"idemp_f7_ptr_{name}")
            site = adapter._need_site(adapter.store.get_site(TENANT))
            for step in cases:
                with self.subTest(adapter=name, kind=step["kind"], prop=step["params"]["property"]):
                    self.assertEqual(adapter._judge(site, step, {"customer"})[:2], ("blocked", "unsupported_value_type"))

    def test_nested_options_and_target_refused_on_relations(self) -> None:
        for name, adapter in self._adapters():
            self._seed_with_relation(adapter, f"idemp_f7_reln_{name}")
            site = adapter._need_site(adapter.store.get_site(TENANT))
            # Control: a well-formed step on the seeded relation passes this rule, so the refusals below are this rule's.
            self.assertNotEqual(adapter._judge(site, _rel_step("/labels/en"), {"customer"})[1], "unsupported_value_type")
            for prop in ("/options/0", "/options/x/y", "/target/x"):
                with self.subTest(adapter=name, prop=prop):
                    self.assertEqual(adapter._judge(site, _rel_step(prop), {"customer"})[:2], ("blocked", "unsupported_value_type"))


class TestSettablePropertiesAllowList(_Base):
    """Eldon's review of #280 (Fable 5.2), Medium 1 and Low 4: `field.set_property /id` renamed a field onto a link
    field's id (no gate), so the `/options` non-link proof read the wrong field; and the entity deny list let
    `/Fields`, `/fields ` and `/%66ields` plan. A set_property step may now name only a Blueprint property of its
    element (the schema has `additionalProperties: false`), never the identity or the element lists."""

    def test_eldon_rename_repro_refused(self) -> None:
        steps = [
            {**_field_step(1, "customer", "ref_link", kind="field.set_property"), "params": _set("/id", "zzz_old", "ref_link")},
            {**_field_step(1, "customer", "tier", kind="field.set_property"), "params": _set("/id", "ref_link", "tier")},
        ]
        self._refuse_all(steps, "rename", apply=True)

    def test_identity_and_unknown_properties_refused(self) -> None:
        field = ("/id", "/id/x", "/Type", "/type ", "/%74ype", "/indexed", "/unknown", "/fields")
        entity = ("/Fields", "/fields ", "/%66ields", "/unknown", "/provenance ", "/Labels")
        relation = ("/id", "/id/x", "/unknown", "/Target", "/fields")
        steps = [{**_field_step(1, "customer", "ref_link", kind="field.set_property"), "params": _set(p)} for p in field]
        steps += [_entity_step("entity.set_property", CUSTOMER, _set(p)) for p in entity]
        for name, adapter in self._adapters():
            self._seed_with_relation(adapter, f"idemp_f7_allow_{name}")
            site = adapter._need_site(adapter.store.get_site(TENANT))
            self.assertNotEqual(adapter._judge(site, _rel_step("/labels/en"), {"customer"})[1], "unsupported_value_type")
            for step in steps + [_rel_step(p) for p in relation]:
                with self.subTest(adapter=name, kind=step["kind"], prop=step["params"]["property"]):
                    self.assertEqual(adapter._judge(site, step, {"customer"})[:2], ("blocked", "unsupported_value_type"))

    def test_allow_lists_match_the_blueprint_schema(self) -> None:
        import json
        from pathlib import Path
        from change_engine.adapter.engine import SETTABLE_PROPERTIES

        root = next(p for p in Path(__file__).resolve().parents if (p / "contracts" / "blueprint.schema.json").exists())
        defs = json.loads((root / "contracts" / "blueprint.schema.json").read_text())["$defs"]
        for kind, element, excluded in (
            ("entity.set_property", "entity", {"id", "fields", "relations"}),
            ("field.set_property", "field", {"id"}),
            ("relation.set_property", "relation", {"id"}),
        ):
            # `options` on a relation is the adapter's own link-target property (frappe_backend maps it), kept under the
            # `/options` target checks; it is not a Blueprint relation property.
            extra = {"options"} if element == "relation" else set()
            with self.subTest(kind=kind):
                self.assertIs(defs[element].get("additionalProperties"), False)
                self.assertEqual(SETTABLE_PROPERTIES[kind], (frozenset(defs[element]["properties"]) - excluded) | extra)

    def test_every_allowed_field_and_relation_property_still_plans_past_the_rule(self) -> None:
        from change_engine.adapter.engine import SETTABLE_PROPERTIES

        for name, adapter in self._adapters():
            self._seed_with_fields(adapter, f"idemp_f7_allowok_{name}")
            site = adapter._need_site(adapter.store.get_site(TENANT))
            for prop in sorted(SETTABLE_PROPERTIES["field.set_property"] - {"type", "options", "target"}):
                step = {**_field_step(1, "customer", "ref_link", kind="field.set_property"), "params": _set("/" + prop, True)}
                with self.subTest(adapter=name, prop=prop):
                    self.assertNotEqual(adapter._judge(site, step, {"customer"})[1], "unsupported_value_type")


if __name__ == "__main__":
    unittest.main()
