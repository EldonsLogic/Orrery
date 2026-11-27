"""BPL-046: the Custom Field the engine inserts must carry the column settings its approved DDL plan used.

Bench finding (BPL-027 class, test_03, step 42 ``entity.add /entities/customer``): the plan for
``custom_customer_code`` (Blueprint ``maxLength`` 20) was built from ``length`` = 20, but
``FrappeDeploymentAdapter.apply_native_custom_field`` built the Custom Field without ``length``, so
the engine emitted ``varchar(140)`` and the dispatch gate refused it ("executed ADD COLUMN clauses
differ from the approved plan").

The fake Frappe below derives the executed ADD COLUMN from the args the adapter hands to
``frappe.get_doc`` (as Frappe's schema sync does from the Custom Field), never from the field
definition, and the approved plan comes from the planning path for the same field definition. The
gate itself is unchanged: a Custom Field that still differs from the plan is refused before dispatch.
"""
from __future__ import annotations

import os
import sys
import types
import unittest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from change_engine.api.endpoints import FrappeDeploymentAdapter  # noqa: E402
from change_engine.guarded_apply.ddl_plan_gate import (  # noqa: E402
    SimulatedDbColumn,
    SimulatedMariaDBTable,
    inspect_frappe_ddl_plan,
)
from change_engine.tests.test_erp_027_decimal_drift import _LiveDb, _col  # noqa: E402

_DOCTYPE = "Item"
_DEP = "dep-bpl046"


class _Harness:
    """Live-mode adapter over a fake Frappe whose schema sync reads the inserted Custom Field."""

    def __init__(self) -> None:
        self.db = _LiveDb()
        self.captured: list[dict] = []
        self.module = types.SimpleNamespace(db=self.db, clear_cache=lambda **kw: None, get_doc=self._get_doc)
        self.adapter = FrappeDeploymentAdapter(frappe_module=self.module, in_memory=False)

    def _get_doc(self, args):
        self.captured.append(dict(args))

        def insert(ignore_permissions=True):
            column = SimulatedDbColumn(
                table=SimulatedMariaDBTable(args["dt"]),
                fieldname=args["fieldname"],
                fieldtype=args.get("fieldtype") or "Data",
                length=args.get("length"),
                default=args.get("default"),
                precision=args.get("precision"),
                options=args.get("options"),
            )
            definition = column.get_definition()
            self.db.sql_ddl(f"ALTER TABLE `tab{args['dt']}` ADD COLUMN `{args['fieldname']}` {definition}")
            self.db.schema["columns"][args["fieldname"]] = _col(definition.split(" ", 1)[0])
            self.db.schema["order"].append(args["fieldname"])
            self.db.inserted.add(args["fieldname"])

        return types.SimpleNamespace(insert=insert)

    def deploy(self, field_def: dict, plan_def: dict | None = None) -> list[str]:
        plan = inspect_frappe_ddl_plan(_DOCTYPE, plan_def or field_def, offline_simulator=True)
        self.adapter.take_snapshot(_DOCTYPE, field_def["fieldname"], _DEP)
        self.adapter._approved_ddl[_DEP] = list(plan.statements)
        self.adapter.apply_native_custom_field(_DEP, _DOCTYPE, field_def)
        return list(plan.statements)


class TestCustomFieldCarriesPlannedColumnSettings(unittest.TestCase):
    def test_max_length_reaches_the_custom_field_and_the_executed_ddl_matches_the_plan(self) -> None:
        h = _Harness()
        approved = h.deploy({"fieldname": "custom_customer_code", "fieldtype": "Data", "length": 20})
        self.assertEqual(h.captured[0].get("length"), 20)
        self.assertEqual(h.db.ddl_log, approved)
        self.assertEqual(h.adapter._executed_ddl[_DEP], approved)

    def test_long_max_length_widens_the_column_as_planned(self) -> None:
        h = _Harness()
        approved = h.deploy({"fieldname": "custom_note", "fieldtype": "Data", "length": 200})
        self.assertIn("varchar(200)", approved[0])
        self.assertEqual(h.db.ddl_log, approved)

    def test_precision_reaches_the_custom_field_and_the_executed_ddl_matches_the_plan(self) -> None:
        h = _Harness()
        approved = h.deploy({"fieldname": "custom_credit_limit", "fieldtype": "Currency", "precision": 2})
        self.assertEqual(h.captured[0].get("precision"), 2)
        self.assertEqual(h.db.ddl_log, approved)

    def test_field_without_length_keeps_the_default_column(self) -> None:
        h = _Harness()
        approved = h.deploy({"fieldname": "custom_x", "fieldtype": "Data"})
        self.assertIn("varchar(140)", approved[0])
        self.assertEqual(h.db.ddl_log, approved)

    def test_gate_still_refuses_a_custom_field_that_differs_from_the_plan(self) -> None:
        h = _Harness()
        with self.assertRaisesRegex(ValueError, "DDL rejected before execution: executed ADD COLUMN clauses differ"):
            h.deploy({"fieldname": "custom_x", "fieldtype": "Data", "length": 200},
                     plan_def={"fieldname": "custom_x", "fieldtype": "Data", "length": 20})
        self.assertEqual(h.db.ddl_log, [], "the mismatching statement is never dispatched")


if __name__ == "__main__":
    unittest.main()
