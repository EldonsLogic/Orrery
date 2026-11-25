"""SEC-022 / BPL-032 review follow-up 5 (ADR-0051), from Eldon's review of merged PR #262.

Plan-time refusal of steps whose pointer does not start at a known Blueprint section or setting root, so the
adapter's internal `_typeChangedPointers` record in `site.config` can never be a step target; empty pointers,
`/` and pointers with empty segments are refused with a reason code, never an exception. Synthetic data only.
"""
from __future__ import annotations

import unittest
from unittest import mock

from change_engine.adapter.engine import ALLOWED_POINTER_ROOTS, SECTION_OF, SETTINGS, STEP_KINDS
from change_engine.tests.test_sec_022_review_followups_4 import (
    _AdapterPlanBase,
    _artifact,
    _ctx,
    _entity,
    _field_step,
    _inverse_for,
    _relation_step,
)

REFUSED = ("blocked", "unsupported_value_type", "rejected")


_PHASE = {
    "settings.set": 1, "component.enable": 2, "component.configure": 2, "location.upsert": 3, "entity.add": 4,
    "option.add": 5, "entity.set_property": 6, "option.reorder": 6, "role.upsert": 7, "workflow.upsert": 8,
    "approval.upsert": 9, "report.upsert": 10, "report.disable": 11, "approval.disable": 12, "workflow.disable": 13,
    "role.disable": 14, "option.quarantine": 15, "entity.quarantine": 16, "location.disable": 17,
    "component.disable": 18,
}


def _step(seq: int, kind: str, pointer: str, params: dict, *, ddl: str = "none", impact: str = "config") -> dict:
    section = kind.split(".")[0]
    return {
        "seq": seq,
        "phase": _PHASE[kind],
        "kind": kind,
        "subject": {"kind": "company" if section == "settings" else section, "id": None if section == "settings" else "x", "parents": []},
        "pointer": pointer,
        "impact": impact,
        "ddlImpact": ddl,
        "reversible": True,
        "params": params,
        "sourceOps": [pointer],
    }


def _type_change(seq: int) -> dict:
    step = _field_step(seq, "customer", "note", kind="field.set_property")
    step["pointer"] = "/entities/customer/fields/note"
    step["params"] = {"property": "/type", "before": "string", "after": "integer"}
    step["impact"], step["ddlImpact"] = "data_shape", "semantic"
    return step


class TestAllowedRoots(unittest.TestCase):
    def test_allowed_roots_are_exactly_the_sections_and_settings_the_step_kinds_target(self) -> None:
        self.assertEqual(
            set(ALLOWED_POINTER_ROOTS),
            {"components", "locations", "entities", "roles", "workflows", "approvals", "reports", *SETTINGS},
        )
        self.assertEqual(set(SETTINGS), {"company", "compliance", "i18n"})
        self.assertEqual(set(SECTION_OF.values()), set(ALLOWED_POINTER_ROOTS) - set(SETTINGS))
        self.assertFalse([r for r in ALLOWED_POINTER_ROOTS if r.startswith("_")])
        self.assertTrue(all(k in STEP_KINDS for k in ("location.upsert", "option.reorder")))


class _RefusalBase(_AdapterPlanBase):
    def _planned(self, adapter, steps: list[dict], key: str, *, with_type_change: bool) -> dict:
        rev1 = self._seed_customer(adapter, key)
        if with_type_change:
            # Apply a `/type` change so the adapter records `_typeChangedPointers` in the site config.
            for n, steps_n in ((2, [_field_step(1, "customer", "note")]), (3, [_type_change(1)])):
                nxt = {"hash": "sha256:" + str(n) * 64, "revision": n}
                inv = _inverse_for(rev1, nxt, [_field_step(1, "customer", "note", kind="field.quarantine")])
                art = _artifact(steps_n, base=rev1, target=nxt, inverse=inv)
                pl = adapter.call("plan", _ctx(), {"artifact": art})
                self.assertTrue(pl["ok"] and pl["result"]["verdict"] != "rejected", pl)
                ap = adapter.call("apply", _ctx(), {
                    "idempotencyKey": f"{key}_ap{n}",
                    "planToken": pl["result"]["planToken"],
                    "artifact": art,
                    "approvals": {"changeApproved": "01J00000000000000000000010", "gateApproved": "01J00000000000000000000011"},
                })
                self.assertTrue(ap["ok"] and ap["result"]["status"] == "applied", ap)
                rev1 = nxt
        rev3 = {"hash": "sha256:" + "9" * 64, "revision": 4 if with_type_change else 2}
        inv = _inverse_for(rev1, rev3, [_field_step(1, "customer", "note", kind="field.quarantine")])
        art = _artifact(steps, base=rev1, target=rev3, inverse=inv)
        site_before = adapter.call("export_config", _ctx(), {})
        planned = adapter.call("plan", _ctx(), {"artifact": art})
        self.assertTrue(planned["ok"], planned)
        self.assertEqual(adapter.call("export_config", _ctx(), {})["result"], site_before["result"], "plan must not write")
        status = adapter.call("site_status", _ctx(), {})
        self.assertTrue(status["ok"], status)
        self.assertNotEqual(status["result"].get("state"), "recovery_required", status)
        return planned["result"]

    def _assert_refused(self, steps: list[dict], label: str, *, with_type_change: bool) -> None:
        seen = {}
        for name, adapter in self._adapters():
            with self.subTest(case=label, adapter=name, type_change=with_type_change):
                result = self._planned(adapter, steps, f"idemp_f5_{abs(hash((label, name, with_type_change)))}", with_type_change=with_type_change)
                got = [(s["disposition"], s.get("reasonCode")) for s in result["steps"]]
                seen[name] = got
                self.assertEqual(got, [REFUSED[:2]] * len(steps), result)
                self.assertEqual(result["verdict"], "rejected")
        if len(seen) == 2:
            self.assertEqual(seen["in_memory"], seen["offline_engine"])


class TestUnknownRootsRefusedAtPlan(_RefusalBase):
    def test_steps_aimed_at_the_internal_record_key_are_refused_on_both_adapters(self) -> None:
        cases = {
            "location_upsert_record_child": _step(
                1, "location.upsert", "/_typeChangedPointers/x",
                {"definition": {"id": "x", "kind": "branch", "labels": {"en": "X", "ar": "X"}}},
            ),
            "option_reorder_record": _step(
                1, "option.reorder", "/_typeChangedPointers", {"order": ["a"], "previousOrder": ["a"]},
            ),
            "settings_set_record": _step(
                1, "settings.set", "/_typeChangedPointers", {"property": "/x", "before": None, "after": 1},
            ),
        }
        for label, step in cases.items():
            for with_type_change in (False, True):
                self._assert_refused([step], label, with_type_change=with_type_change)

    def test_underscore_and_unknown_roots_are_refused(self) -> None:
        for root in ("_internal", "_", "settings", "retained", "branding", "integrations", "meta", "assistants", "Entities", "entity"):
            step = _step(1, "location.upsert", f"/{root}/x", {"definition": {"id": "x"}})
            self._assert_refused([step], f"root_{root}", with_type_change=False)

    def test_empty_and_malformed_pointers_are_refused_not_raised(self) -> None:
        # Pointers the contract pattern `^(/[^/]*)*$` accepts reach the engine check and get a reason code.
        for ptr in ("", "/", "//", "/entities//fields", "/entities/", "/locations/", "/company/", "/i18n//x", "/ ", "/x"):
            for kind, params in (
                ("location.upsert", {"definition": {"id": "x"}}),
                ("option.reorder", {"order": ["a"], "previousOrder": ["a"]}),
                ("settings.set", {"property": "/x", "before": None, "after": 1}),
            ):
                step = _step(1, kind, ptr, params)
                self._assert_refused([step], f"ptr_{ptr!r}_{kind}", with_type_change=False)

    def test_pointers_outside_the_contract_pattern_are_refused_cleanly_by_validation(self) -> None:
        for name, adapter in self._adapters():
            rev1 = self._seed_customer(adapter, f"idemp_f5_bad_{name}")
            rev2 = {"hash": "sha256:" + "6" * 64, "revision": 2}
            inv = _inverse_for(rev1, rev2, [_field_step(1, "customer", "note", kind="field.quarantine")])
            for ptr in ("entities/customer", "x"):
                with self.subTest(adapter=name, pointer=ptr):
                    step = _step(1, "location.upsert", ptr, {"definition": {"id": "x"}})
                    res = adapter.call("plan", _ctx(), {"artifact": _artifact([step], base=rev1, target=rev2, inverse=inv)})
                    self.assertFalse(res["ok"], res)
                    self.assertEqual(res["error"]["code"], "invalid_request", res)


class TestValidPointerKindsStillPlan(_AdapterPlanBase):
    def test_every_known_root_plans_on_both_adapters(self) -> None:
        for name, adapter in self._adapters():
            with self.subTest(adapter=name):
                rev1 = self._seed_customer(adapter, f"idemp_f5_ok_{name}")
                rev2 = {"hash": "sha256:" + "6" * 64, "revision": 2}
                inv = _inverse_for(rev1, rev2, [_field_step(1, "customer", "note", kind="field.quarantine")])
                steps = [
                    _entity(1, "widget"),
                    _field_step(2, "customer", "note"),
                    _step(3, "location.upsert", "/locations/hq", {"definition": {"id": "hq", "kind": "branch", "labels": {"en": "HQ", "ar": "HQ"}}}),
                    _step(4, "settings.set", "/company", {"property": "/tradeName", "before": None, "after": "Synthetic Co"}),
                ]
                steps[3]["phase"] = 1
                art = _artifact(steps, base=rev1, target=rev2, inverse=inv)
                res = adapter.call("plan", _ctx(), {"artifact": art})
                self.assertTrue(res["ok"], res)
                dispositions = {s["seq"]: (s["disposition"], s.get("reasonCode")) for s in res["result"]["steps"]}
                for seq in (1, 2, 3, 4):
                    self.assertEqual(dispositions[seq][1] != "unsupported_value_type", True, dispositions)
                    self.assertEqual(dispositions[seq][0], "ok", dispositions)

    def test_known_roots_pass_the_root_check_for_every_kind(self) -> None:
        for kind, support in STEP_KINDS.items():
            if support == "unsupported":
                continue
            section = kind.split(".")[0]
            root = {"settings": "company", "option": "entities"}.get(section, SECTION_OF.get(section, "entities"))
            self.assertIn(root, ALLOWED_POINTER_ROOTS, kind)


_DEF = {"id": "x", "labels": {"en": "X", "ar": "X"}}
_OPT_COLL = "/entities/customer/fields/status/options"


def _params(kind: str) -> dict:
    if kind.endswith("reorder"):
        return {"order": ["a"], "previousOrder": ["a"]}
    if kind.endswith(("set_property", ".configure", "settings.set")):
        # set_property kinds name only a Blueprint property of their element (ADR-0051 item 8); `/labels` is one for all.
        return {"property": "/labels" if kind.endswith("set_property") else "/x", "before": None, "after": 1}
    return {"definition": {**_DEF, "entity": "customer"} if kind == "workflow.upsert" else dict(_DEF)}


# Element-level kinds, and the shortest pointer each needs (ADR-0051 item 7).
BARE = {
    "location.upsert": ["/locations", "/company", "/entities"],
    "location.disable": ["/locations"],
    "entity.quarantine": ["/entities"],
    "entity.set_property": ["/entities"],
    "role.upsert": ["/roles"],
    "role.disable": ["/roles"],
    "workflow.upsert": ["/workflows"],
    "workflow.disable": ["/workflows"],
    "approval.upsert": ["/approvals"],
    "approval.disable": ["/approvals"],
    "report.upsert": ["/reports"],
    "report.disable": ["/reports"],
    "component.enable": ["/components"],
    "component.configure": ["/components"],
    "component.disable": ["/components"],
    "option.add": ["/entities", "/entities/customer", "/entities/customer/fields/status", _OPT_COLL],
    "option.quarantine": ["/entities", "/entities/customer", "/entities/customer/fields/status", _OPT_COLL],
    "option.reorder": ["/entities", "/entities/customer", "/entities/customer/fields", "/entities/customer/fields/status"],
}


class TestBareRootsRefusedAtPlan(_RefusalBase):
    def test_element_level_steps_on_a_bare_root_or_short_pointer_are_refused_on_both_adapters(self) -> None:
        for kind, pointers in BARE.items():
            for ptr in pointers:
                self._assert_refused([_step(1, kind, ptr, _params(kind))], f"bare_{kind}_{ptr}", with_type_change=False)

    def test_reported_examples_refused_with_type_change_record_present(self) -> None:
        for kind, ptr in (
            ("location.upsert", "/locations"), ("location.upsert", "/company"),
            ("entity.quarantine", "/entities"), ("role.disable", "/roles"),
        ):
            self._assert_refused([_step(1, kind, ptr, _params(kind))], f"rep_{kind}_{ptr}", with_type_change=True)

    def test_leading_slash_is_refused_by_the_engine_without_schema_validation(self) -> None:
        # With `jsonschema` unavailable the contract pattern is not enforced; `_judge` must refuse on its own.
        from change_engine.adapter import contracts_support as cs

        for name, adapter in self._adapters():
            rev1 = self._seed_customer(adapter, f"idemp_f5_slash_{name}")  # seeded with validation on
            rev2 = {"hash": "sha256:" + "6" * 64, "revision": 2}
            inv = _inverse_for(rev1, rev2, [_field_step(1, "customer", "note", kind="field.quarantine")])
            for ptr in ("x/locations/hq", "locations/hq", "x/company", "entities/customer"):
                with self.subTest(adapter=name, pointer=ptr):
                    step = _step(1, "location.upsert", ptr, _params("location.upsert"))
                    art = _artifact([step], base=rev1, target=rev2, inverse=inv)
                    with mock.patch.object(cs, "_validator_for", lambda _ref: None):
                        res = adapter.call("plan", _ctx(), {"artifact": art})
                    if res["ok"]:
                        got = [(s["disposition"], s.get("reasonCode")) for s in res["result"]["steps"]]
                        self.assertEqual(got, [REFUSED[:2]], res)
                    else:
                        self.assertEqual(res["error"]["code"], "invalid_request", res)

    def test_min_segments_per_kind(self) -> None:
        from change_engine.adapter.engine import min_pointer_segments

        expected = {
            "settings.set": 1, "field.reorder": 3, "option.reorder": 5, "option.add": 6, "option.quarantine": 6,
            "field.add": 4, "field.set_property": 4, "field.quarantine": 4,
            "relation.add": 4, "relation.set_property": 4, "relation.quarantine": 4,
        }
        for kind in STEP_KINDS:
            self.assertEqual(min_pointer_segments(kind), expected.get(kind, 2), kind)


class TestCollectionLevelKindsStillPlan(_RefusalBase):
    def test_valid_shapes_of_every_kind_are_not_refused_as_unsupported_value_type(self) -> None:
        cases = [
            _step(1, "settings.set", "/company", _params("settings.set")),
            _step(1, "settings.set", "/compliance", _params("settings.set")),
            _step(1, "settings.set", "/i18n", _params("settings.set")),
            _step(1, "settings.set", "/company/x", _params("settings.set")),
            _step(1, "option.reorder", _OPT_COLL, _params("option.reorder")),
            _step(1, "option.add", _OPT_COLL + "/a", _params("option.add")),
            _step(1, "option.quarantine", _OPT_COLL + "/a", _params("option.quarantine")),
            _field_step(1, "customer", "note", kind="field.reorder"),
            _field_step(1, "customer", "note", kind="field.add"),
            _field_step(1, "customer", "note", kind="field.set_property"),
            _field_step(1, "customer", "note", kind="field.quarantine"),
            _relation_step(1, "customer", "rel", kind="relation.add"),
            _relation_step(1, "customer", "rel", kind="relation.set_property"),
            _relation_step(1, "customer", "rel", kind="relation.quarantine"),
        ]
        for kind in BARE:
            if kind.startswith("option."):
                continue
            cases.append(_step(1, kind, f"/{SECTION_OF[kind.split('.')[0]]}/widget", _params(kind)))
        for name, adapter in self._adapters():
            rev1 = self._seed_customer(adapter, f"idemp_f5_valid_{name}")
            rev2 = {"hash": "sha256:" + "6" * 64, "revision": 2}
            inv = _inverse_for(rev1, rev2, [_field_step(1, "customer", "note", kind="field.quarantine")])
            for step in cases:
                with self.subTest(adapter=name, kind=step["kind"], pointer=step["pointer"]):
                    res = adapter.call("plan", _ctx(), {"artifact": _artifact([step], base=rev1, target=rev2, inverse=inv)})
                    self.assertTrue(res["ok"], res)
                    self.assertNotEqual(res["result"]["steps"][0].get("reasonCode"), "unsupported_value_type", res)


if __name__ == "__main__":
    unittest.main()
