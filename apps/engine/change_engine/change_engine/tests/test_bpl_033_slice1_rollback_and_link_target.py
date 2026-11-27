"""BPL-033 slice 1: a clean refusal compensates back to the exact prior state, and a Link to a missing type is refused.

Defect 1 (BPL-027 bench, steps 56 and 57): a field deployment the guarded sequence refuses before any write (REJECTED at
inspect, or FAILED_CLEAN after the engine's own validation raised before DDL) was reported as a step with possible effects,
so `_compensate` stopped before undoing anything and the apply ended recovery_required. Defect 2 (step 57): a Link field
whose target type does not exist reached the engine, which raised. Offline, on the simulated engine. Synthetic data only.
"""
from __future__ import annotations

import contextlib
import unittest
from unittest import mock

from change_engine.adapter import ChangeEngineAdapter, FrappeBackendError, FrappeRuntimeBackend, FrappeSiteResolver
from change_engine.adapter.mapping import ADAPTER_DOCTYPE_MODULE
from change_engine.api.endpoints import FrappeDeploymentAdapter
from change_engine.guarded_apply.ddl_plan_gate import DDLPlanInspection
from change_engine.tests import test_bpl_027_fixture_real_adapter as bpl027
from change_engine.tests.ci_engine_fake import CaseInsensitiveEngine
from change_engine.tests.test_bpl_031_entity_add_existing_doctype import (
    TENANT,
    backend_for,
    contract_doctypes,
    engine,
    entity,
    field_add_step,
    setUpModule,  # noqa: F401  (starts the test environment patch)
    tearDownModule,  # noqa: F401
    written_state,
)
from change_engine.tests.test_bpl_041_check_ready_refusals import entity_step, no_writes, relation_step

APPROVALS = {"changeApproved": "01J00000000000000000000010", "gateApproved": "01J00000000000000000000011",
             "teamReviewed": "01J00000000000000000000012"}


@contextlib.contextmanager
def engine_validation_error(eng, doctype: str, fieldname: str):
    """The engine refuses the Custom Field insert before any DDL (as WrongOptionsDoctypeLinkError does on the bench)."""
    real = eng.get_doc

    def get_doc(payload, *a, **kw):
        if isinstance(payload, dict) and payload.get("doctype") == "Custom Field" and (payload.get("dt"), payload.get("fieldname")) == (doctype, fieldname):
            raise RuntimeError("simulated engine validation error")
        return real(payload, *a, **kw)

    eng.get_doc = get_doc
    try:
        yield
    finally:
        eng.__dict__.pop("get_doc", None)


@contextlib.contextmanager
def ddl_gate_refusal(doctype: str, fieldname: str):
    """The DDL gate refuses the plan at inspect (as for the unapproved ADD INDEX of bench step 56): REJECTED, nothing written."""
    real = FrappeDeploymentAdapter.inspect_ddl_plan

    def inspect(self, dt, field_def):
        if (dt, field_def.get("fieldname")) == (doctype, fieldname):
            return DDLPlanInspection(inspectable=True, statements=["ALTER TABLE x ADD COLUMN y, ADD INDEX z"],
                                     is_approved_additive_only=False)
        return real(self, dt, field_def)

    with mock.patch.object(FrappeDeploymentAdapter, "inspect_ddl_plan", inspect):
        yield


REFUSALS = {"engine_validation": engine_validation_error, "ddl_gate": lambda eng, dt, fn: ddl_gate_refusal(dt, fn)}
EXPECTED_ERROR = {"engine_validation": ("engine_unavailable", {}),
                  "ddl_gate": ("plan_rejected", {"reasonCode": "storage_not_additive"})}


class TestCleanFieldRefusalIsSideEffectFree(unittest.TestCase):
    def refuse(self, eng, step: dict, doctype: str, fieldname: str, how: str) -> FrappeBackendError:
        with REFUSALS[how](eng, doctype, fieldname), self.assertRaises(FrappeBackendError) as err:
            backend_for(eng).execute_step(TENANT, step)
        return err.exception

    def test_a_refused_first_field_of_an_entity_add_writes_nothing_and_says_so(self) -> None:
        for how in REFUSALS:
            eng = engine()
            before = written_state(eng)
            got = self.refuse(eng, entity_step(1, entity("customer", ("vat_number", "string"))), "Customer", "custom_vat_number", how)
            self.assertTrue(got.side_effect_free, how)
            self.assertEqual((got.code, got.details), EXPECTED_ERROR[how])
            self.assertEqual(written_state(eng), before, f"{how}: the pending intent rows must not stay behind")

    def test_a_plan_the_gate_cannot_inspect_stays_fail_closed(self) -> None:
        eng = engine()
        blind = DDLPlanInspection(inspectable=False, statements=[], is_approved_additive_only=False)
        with mock.patch.object(FrappeDeploymentAdapter, "inspect_ddl_plan", lambda self, dt, fd: blind), \
                self.assertRaises(FrappeBackendError) as err:
            backend_for(eng).execute_step(TENANT, entity_step(1, entity("customer", ("vat_number", "string"))))
        self.assertEqual(err.exception.code, "engine_unavailable")
        self.assertFalse(err.exception.side_effect_free)

    def test_a_refused_second_field_after_the_first_was_created_is_not_side_effect_free(self) -> None:
        for how in REFUSALS:
            eng = engine()
            step = entity_step(1, entity("customer", ("vat_number", "string"), ("cr_number", "string")))
            got = self.refuse(eng, step, "Customer", "custom_cr_number", how)
            self.assertFalse(got.side_effect_free, how)
            self.assertIn("custom_vat_number", {r["fieldname"] for r in eng.rows("Custom Field")}, how)

    def test_a_refused_field_add_is_side_effect_free_unless_it_created_the_type(self) -> None:
        for how in REFUSALS:
            eng = engine()
            got = self.refuse(eng, field_add_step("customer", {"id": "note", "type": "string"}), "Customer", "custom_note", how)
            self.assertTrue(got.side_effect_free, how)
            eng = engine()
            got = self.refuse(eng, field_add_step("brand_new", {"id": "note", "type": "string"}), "Brand New", "custom_note", how)
            self.assertFalse(got.side_effect_free, f"{how}: the step created the type before the refusal")


def fixture_engine() -> CaseInsensitiveEngine:
    """The contract's built-in types, plus Sales Quote as an adapter-owned type: step 57 links it before step 59 creates it
    (Q-691), which check_ready now refuses up front; with the type present the apply gets past step 57."""
    eng = CaseInsensitiveEngine("bpl033.localhost")
    for dt in sorted(set(contract_doctypes().values())):
        if not eng.db.exists("DocType", dt):
            eng.add_doctype(dt, module="Selling", custom=0)
    eng.add_doctype("Sales Quote", module=ADAPTER_DOCTYPE_MODULE, custom=1)
    real = eng.make_property_setter

    def make_property_setter(args=None, **kwargs):
        """The engine's rule (HiddenAndMandatoryWithoutDefaultError, seen on the bench): a mandatory field cannot be hidden."""
        ps = dict(args or kwargs)
        if (ps["property"], int(ps["value"])) == ("hidden", 1):
            key = (ps["doctype"], ps["fieldname"])
            setters = [r for r in eng.rows("Property Setter") if (r["doc_type"], r["field_name"], r["property"]) == (*key, "reqd")]
            fields = [r for r in eng.rows("Custom Field") if (r["dt"], r["fieldname"]) == key]
            reqd = setters[-1]["value"] if setters else (fields[0].get("reqd") if fields else 0)
            if int(reqd or 0):
                raise RuntimeError("simulated HiddenAndMandatoryWithoutDefaultError")
        return real(args, **kwargs)

    eng.make_property_setter = make_property_setter
    return eng


# The bench cases: the first new field of step 56 (DDL gate, before BPL-046's index sync) and of step 57 (the engine's Link
# validation). Step 56 holds required fields, so undoing it after the step 57 refusal exercises the quarantine order.
REFUSED_AT = {56: ("Sales Invoice Item", "custom_item"), 57: ("Sales Order", "custom_sales_quote")}


class TestFixtureRollbackAfterACleanRefusal(unittest.TestCase):
    """The BPL-027 trading fixture through the adapter: step 56 or 57 is refused cleanly after the steps before it applied.
    Every earlier step is undone and the export is the pre-apply one."""

    def run_fixture(self, eng, how: str | None, seq: int = 56) -> tuple[dict, str]:
        backend = FrappeRuntimeBackend(site_resolver=FrappeSiteResolver(site_map={bpl027.TENANT: "bpl033.localhost"}),
                                       frappe_factory=lambda: eng, offline_ddl_simulator=True)
        adapter = ChangeEngineAdapter(test_hooks=False, frappe_backend=backend)
        art = bpl027.compile_for_adapter(bpl027.apply_ready(bpl027.load_fixture()))
        self.assertEqual([s["pointer"] for s in art["steps"] if s["seq"] == 56], ["/entities/sales_invoice_line"])
        prov = adapter.call("provision_site", bpl027.ctx(), {"idempotencyKey": "idemp_bpl033s1_prov", "engineTarget": art["engineTarget"],
                            "blueprintId": art["blueprint"]["id"], "siteClass": "sandbox", "countryPack": "sa"})
        self.assertTrue(prov["ok"], prov)
        pre = adapter.call("export_config", bpl027.ctx(), {})["result"]["exportHash"]
        plan = adapter.call("plan", bpl027.ctx(), {"artifact": art})["result"]
        ctx = REFUSALS[how](eng, *REFUSED_AT[seq]) if how else contextlib.nullcontext()
        with ctx:
            out = adapter.call("apply", bpl027.ctx(), {"idempotencyKey": "idemp_bpl033s1_apply", "artifact": art,
                                                       "planToken": plan["planToken"], "approvals": APPROVALS})
        self.assertTrue(out["ok"], out)
        after = adapter.call("export_config", bpl027.ctx(), {})["result"]["exportHash"]
        return out["result"], pre if after == pre else f"{pre} != {after}"

    def test_the_fixture_applies_offline(self) -> None:  # the refusal below is the only difference
        out, _ = self.run_fixture(fixture_engine(), None)
        self.assertEqual(out["status"], "applied", out.get("error"))

    def test_a_clean_refusal_at_step_56_or_57_compensates_every_earlier_step(self) -> None:
        for how, seq in ((how, seq) for how in REFUSALS for seq in REFUSED_AT):
            with self.subTest(how=how, seq=seq):
                self.assert_compensated(how, seq)

    def assert_compensated(self, how: str, seq: int) -> None:
        eng = fixture_engine()
        out, pre = self.run_fixture(eng, how, seq)
        self.assertEqual(out["status"], "compensated", (how, out.get("error"), out["stages"]))
        self.assertEqual(out["site"]["state"], "ready", how)
        self.assertEqual(out["exportHash"], pre, how)
        by_seq = {s["seq"]: s["status"] for s in out["steps"]}
        self.assertEqual({by_seq[i] for i in range(1, seq)}, {"compensated"}, how)
        self.assertEqual(by_seq[seq], "failed", how)
        self.assertEqual((out["error"]["code"], out["error"]["details"]), (EXPECTED_ERROR[how][0], {"stepSeq": seq, **EXPECTED_ERROR[how][1]}))
        # engine side: nothing of the refused step, and every field the earlier entity steps added is hidden (quarantined)
        fields = {(r["dt"], r["fieldname"]): r for r in eng.rows("Custom Field")}
        self.assertNotIn(REFUSED_AT[seq], fields, how)
        hidden = {(r["doc_type"], r["field_name"]) for r in eng.rows("Property Setter")
                  if r.get("property") == "hidden" and str(r.get("value")) == "1"}
        added = {k for k in fields if k[1].startswith("custom_")}
        self.assertTrue(added, how)
        self.assertEqual(added - hidden, set(), how)


def link_entity(entity_id: str, target: str) -> dict:
    definition = entity(entity_id, ("note", "string"))
    definition["fields"].append({"id": "ref", "type": "link", "target": target})
    return definition


class TestMissingLinkTargetIsRefusedBeforeAnyWrite(unittest.TestCase):
    """A Link to a type that does not exist yet is refused with `subject_missing` (contract 5.4) and the target pointer, by
    check_ready and again by the execute path, before any write."""

    OFFENDING = [
        entity_step(1, link_entity("sales_order", "sales_quote")),  # mapped built-in type, the bench step 57 case
        entity_step(1, link_entity("site_visit", "sales_quote")),  # an unmapped type the adapter would create
        field_add_step("customer", {"id": "quote", "type": "link", "target": "sales_quote"}),
        relation_step(1, "customer", {"id": "quote", "target": "sales_quote"}),
    ]

    def assert_refused(self, err: FrappeBackendError) -> None:
        self.assertEqual((err.code, err.details), ("plan_rejected", {"reasonCode": "subject_missing", "pointer": "/entities/sales_quote"}))
        self.assertTrue(err.side_effect_free)

    def test_both_paths_refuse_with_nothing_written(self) -> None:
        for step in self.OFFENDING:
            eng = engine()
            with no_writes(self, eng), self.assertRaises(FrappeBackendError) as ready:
                backend_for(eng).check_ready(TENANT, [step])
            self.assert_refused(ready.exception)
            before = written_state(eng)
            with self.assertRaises(FrappeBackendError) as ran:
                backend_for(eng).execute_step(TENANT, step)
            self.assert_refused(ran.exception)
            self.assertEqual(written_state(eng), before, step["pointer"])

    def test_a_target_an_earlier_step_creates_passes_and_a_later_one_does_not(self) -> None:
        quote = entity_step(1, entity("sales_quote", ("quote_date", "date")))
        order = entity_step(2, link_entity("sales_order", "sales_quote"))
        eng = engine()
        with no_writes(self, eng):
            backend_for(eng).check_ready(TENANT, [quote, order])
        for step in (quote, order):
            backend_for(eng).execute_step(TENANT, step)
        self.assertIn(("Sales Order", "custom_ref"), {(r["dt"], r["fieldname"]) for r in eng.rows("Custom Field")})
        eng = engine()
        with no_writes(self, eng), self.assertRaises(FrappeBackendError) as err:
            backend_for(eng).check_ready(TENANT, [{**order, "seq": 1}, {**quote, "seq": 2}])
        self.assert_refused(err.exception)

    def test_a_link_to_the_type_itself_and_to_an_existing_type_pass(self) -> None:
        eng = engine()
        plan = [entity_step(1, link_entity("site_visit", "site_visit")), entity_step(2, link_entity("sales_order", "customer"))]
        with no_writes(self, eng):
            backend_for(eng).check_ready(TENANT, plan)

    def test_through_the_adapter_the_apply_fails_clean_with_the_reason(self) -> None:
        eng = engine()
        backend = backend_for(eng)
        adapter = ChangeEngineAdapter(test_hooks=False, frappe_backend=backend)
        target = {"adapter": bpl027.ADAPTER_ID, "versionSet": "set-example"}
        prov = adapter.call("provision_site", bpl027.ctx(), {"idempotencyKey": "idemp_bpl033s1_lprov", "engineTarget": target,
                            "blueprintId": "bp-offline", "siteClass": "sandbox", "countryPack": "sa"})
        self.assertTrue(prov["ok"], prov)
        defs = [entity("customer", ("vat_number", "string")), link_entity("sales_order", "sales_quote")]
        steps = [{**entity_step(i, d), "phase": 4, "impact": "data_shape", "ddlImpact": "additive", "reversible": True,
                  "subject": {"kind": "entity", "id": d["id"], "parents": []}, "sourceOps": [f"/entities/{d['id']}"]}
                 for i, d in enumerate(defs, start=1)]
        art = bpl027.seal({**bpl027.TestBpl027Offline._two_warehouse_artifact(target), "steps": steps})
        plan = adapter.call("plan", bpl027.ctx(), {"artifact": art})["result"]
        before = written_state(eng)
        out = adapter.call("apply", bpl027.ctx(), {"idempotencyKey": "idemp_bpl033s1_lapply", "artifact": art,
                                                   "planToken": plan["planToken"], "approvals": APPROVALS})["result"]
        self.assertEqual(out["status"], "failed_clean", out)
        self.assertEqual(out["error"]["code"], "plan_rejected")
        self.assertEqual(out["error"]["details"], {"reasonCode": "subject_missing", "pointer": "/entities/sales_quote"})
        self.assertEqual(written_state(eng), before)


if __name__ == "__main__":
    unittest.main()
