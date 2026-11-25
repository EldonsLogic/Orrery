"""SEC-022 / BPL-032 review follow-up 6 (ADR-0051 item 7), from Eldon's review of merged PR #273 (Low 1).

The pointer root must be the root its step kind belongs to: `location.upsert /roles/x`, `location.upsert /company/x`
and `settings.set /entities` are refused at plan time with `unsupported_value_type` on both adapters, with nothing
written and no `recovery_required`. Every valid kind still plans. Synthetic data only.
"""
from __future__ import annotations

import unittest

from change_engine.adapter.engine import ALLOWED_POINTER_ROOTS, KIND_ROOTS, SETTINGS, STEP_KINDS
from change_engine.tests.test_sec_022_review_followups_4 import (
    _AdapterPlanBase,
    _artifact,
    _bpdiff_field_reorder_step,
    _ctx,
    _entity,
    _field_step,
    _inverse_for,
    _relation_step,
)
from change_engine.tests.test_sec_022_review_followups_5 import _OPT_COLL, _params, _step

ENT, ROLES, LOC = "entities", "roles", "locations"
# Written out literally, not derived: the root(s) each kind may target, by the name of its Blueprint section.
EXPECTED_ROOTS = {
    "settings.set": {"company", "compliance", "i18n"},
    "component.enable": {"components"}, "component.configure": {"components"}, "component.disable": {"components"},
    "location.upsert": {LOC}, "location.disable": {LOC},
    "entity.add": {ENT}, "entity.set_property": {ENT}, "entity.quarantine": {ENT},
    "field.add": {ENT}, "field.set_property": {ENT}, "field.reorder": {ENT}, "field.quarantine": {ENT},
    "option.add": {ENT}, "option.reorder": {ENT}, "option.quarantine": {ENT},
    "relation.add": {ENT}, "relation.set_property": {ENT}, "relation.quarantine": {ENT},
    "role.upsert": {ROLES}, "role.disable": {ROLES},
    "workflow.upsert": {"workflows"}, "workflow.disable": {"workflows"},
    "approval.upsert": {"approvals"}, "approval.disable": {"approvals"},
    "report.upsert": {"reports"}, "report.disable": {"reports"},
}


def _valid_steps() -> list[dict]:
    """One valid step per supported or gated kind, each with a pointer under its own root."""
    steps = [
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
        _entity(1, "widget"),
    ]
    for kind, roots in EXPECTED_ROOTS.items():
        if kind.startswith(("settings.", "option.", "field.", "relation.", "entity.add")):
            continue
        steps.append(_step(1, kind, f"/{sorted(roots)[0]}/widget", _params(kind)))
    return steps


def _under(step: dict, root: str) -> dict:
    """The same step with its pointer moved under `root` (everything after the first segment is kept)."""
    moved = dict(step)
    moved["pointer"] = "/" + root + step["pointer"][len("/" + step["pointer"].split("/")[1]):]
    moved["sourceOps"] = [moved["pointer"]]
    return moved


class TestKindRootMapping(unittest.TestCase):
    def test_mapping_is_exactly_the_documented_one(self) -> None:
        supported = {k for k, v in STEP_KINDS.items() if v != "unsupported"}
        self.assertEqual(set(EXPECTED_ROOTS), supported)
        self.assertEqual({k: set(v) for k, v in KIND_ROOTS.items()}, EXPECTED_ROOTS)
        self.assertEqual(set(EXPECTED_ROOTS["settings.set"]), set(SETTINGS))
        used = set().union(*EXPECTED_ROOTS.values())
        self.assertEqual(used, set(ALLOWED_POINTER_ROOTS))

    def test_unsupported_and_unknown_kinds_have_no_root(self) -> None:
        for kind in ("binding.add", "binding.set_property", "binding.disable"):
            self.assertNotIn(kind, KIND_ROOTS)


class _Base(_AdapterPlanBase):
    def _plan_each(self, steps: list[dict], tag: str, *, refused: bool) -> None:
        for name, adapter in self._adapters():
            rev1 = self._seed_customer(adapter, f"idemp_f6_{tag}_{name}")
            rev2 = {"hash": "sha256:" + "6" * 64, "revision": 2}
            inv = _inverse_for(rev1, rev2, [_field_step(1, "customer", "note", kind="field.quarantine")])
            before = adapter.call("export_config", _ctx(), {})["result"]
            for step in steps:
                with self.subTest(adapter=name, kind=step["kind"], pointer=step["pointer"]):
                    res = adapter.call("plan", _ctx(), {"artifact": _artifact([step], base=rev1, target=rev2, inverse=inv)})
                    self.assertTrue(res["ok"], res)
                    got = res["result"]["steps"][0]
                    if refused:
                        self.assertEqual((got["disposition"], got.get("reasonCode")), ("blocked", "unsupported_value_type"), res)
                        self.assertEqual(res["result"]["verdict"], "rejected")
                    else:
                        self.assertNotEqual(got.get("reasonCode"), "unsupported_value_type", res)
            self.assertEqual(adapter.call("export_config", _ctx(), {})["result"], before, "plan must not write")
            status = adapter.call("site_status", _ctx(), {})
            self.assertTrue(status["ok"], status)
            self.assertNotEqual(status["result"].get("state"), "recovery_required", status)


class TestRootTiedToKind(_Base):
    def test_reported_examples_are_refused(self) -> None:
        steps = [
            _step(1, "location.upsert", "/roles/x", _params("location.upsert")),
            _step(1, "location.upsert", "/company/x", _params("location.upsert")),
            _step(1, "settings.set", "/entities", _params("settings.set")),
            _step(1, "settings.set", "/entities/x", _params("settings.set")),
            _step(1, "settings.set", "/locations/x", _params("settings.set")),
            _step(1, "settings.set", "/roles/x", _params("settings.set")),
            _step(1, "role.upsert", "/locations/x", _params("role.upsert")),
            _step(1, "role.disable", "/entities/x", _params("role.disable")),
            _step(1, "entity.quarantine", "/roles/x", _params("entity.quarantine")),
            _step(1, "report.upsert", "/workflows/x", _params("report.upsert")),
        ]
        self._plan_each(steps, "rep", refused=True)

    def test_every_kind_under_every_other_known_root_is_refused(self) -> None:
        steps = []
        for valid in _valid_steps():
            own = EXPECTED_ROOTS[valid["kind"]]
            for root in sorted(ALLOWED_POINTER_ROOTS - own):
                steps.append(_under(valid, root))
        self.assertGreater(len(steps), 200)
        self._plan_each(steps, "matrix", refused=True)

    def test_settings_set_keeps_all_three_settings_roots(self) -> None:
        steps = [_step(1, "settings.set", f"/{r}", _params("settings.set")) for r in sorted(SETTINGS)]
        self._plan_each(steps, "settings", refused=False)

    def test_every_valid_kind_still_plans(self) -> None:
        self._plan_each(_valid_steps(), "valid", refused=False)

    def test_bpdiff_field_reorder_pointer_still_plans(self) -> None:
        self._plan_each([_bpdiff_field_reorder_step(1, "customer", ["a"], ["a"])], "bpdiff", refused=False)


if __name__ == "__main__":
    unittest.main()
