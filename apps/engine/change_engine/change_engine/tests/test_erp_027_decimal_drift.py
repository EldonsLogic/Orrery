"""ERP-027 tests: no false MODIFY COLUMN drift on decimal(21,9) columns in the DDL plan gate.

Phase 0 finding (E0-7 #1): MariaDB reports `COLUMN_DEFAULT = '0.000000000'` for decimal(21,9)
columns that Frappe DocFields declare with no default, so Frappe's `MariaDBTable.alter()` emits
phantom `MODIFY ... decimal(21,9) not null default 0` statements and the gate rejects every
customer-added field on Customer, Sales Order, Sales Invoice and Item.

These tests drive the Frappe-native inspection path (`_inspect_with_frappe_mariadb_table`)
against a small in-process stand-in for Frappe's `MariaDBTable` / `DbColumn` that copies the
comparison logic of Frappe v15 (strict string type compare, `default_changed_for_decimal`),
so the real code path is exercised without a bench. A live-bench run of the same checks is in
the ERP-027 log. Genuine type, precision, scale and default changes must still be flagged.
"""
from __future__ import annotations

import os
import sys
import types
import unittest
from unittest import mock

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from change_engine.guarded_apply.ddl_plan_gate import (  # noqa: E402
    ColumnDesc,
    SimulatedDbColumn,
    SimulatedMariaDBTable,
    _canonical_column_type,
    _inspect_with_frappe_mariadb_table,
    inspect_frappe_ddl_plan,
    validate_ddl_plan,
)

CORE_DOCTYPES = ("Customer", "Sales Order", "Sales Invoice", "Item")


class _FrappeStrictDbColumn(SimulatedDbColumn):
    """Mirrors frappe.database.schema.DbColumn.build_for_alter_table (v15): strict type compare."""

    def build_for_alter_table(self, current_def):
        column_type = self.get_column_type()
        if not column_type:
            return
        if not current_def:
            self.table.add_column.append(self)
            return
        if current_def["type"] != column_type:
            self.table.change_type.append(self)
        if self.default_changed(current_def):
            self.table.set_default.append(self)

    def default_changed(self, current_def):
        # frappe.database.schema.DbColumn.default_changed_for_decimal
        if "decimal" not in current_def["type"]:
            return super().default_changed(current_def)
        cur_default = current_def["default"]
        if cur_default == "NULL":
            cur_default = None
        if cur_default in ("", None) and self.default in ("", None):
            return False
        if cur_default in ("", None):
            try:
                float(self.default)
                return True
            except ValueError:
                return False
        if self.default in ("", None):
            return True
        return float(cur_default) != float(self.default)


class _FrappeStyleTable:
    """Stand-in for frappe.database.mariadb.schema.MariaDBTable; docfields are class-level."""

    docfields: list = []
    live_columns: list = []
    ddl_sink: list = []

    def __init__(self, doctype):
        self.doctype = doctype
        self.columns = {}
        self.current_columns = {}
        self.add_column, self.change_type, self.set_default = [], [], []
        for fname, ftype, default in self.docfields:
            self.columns[fname] = _FrappeStrictDbColumn(self, fname, ftype, default=default)

    def setup_table_columns(self):
        for c in self.live_columns:
            self.current_columns[c["name"].lower()] = ColumnDesc(**c)

    def alter(self):
        for col in self.columns.values():
            col.build_for_alter_table(self.current_columns.get(col.fieldname.lower()))
        parts = [f"ADD COLUMN `{c.fieldname}` {c.get_definition()}" for c in self.add_column]
        parts += [
            f"MODIFY `{c.fieldname}` {c.get_definition(for_modification=True)}"
            for c in dict.fromkeys(self.change_type + self.set_default)
        ]
        if parts:
            import frappe

            frappe.db.sql_ddl(f"ALTER TABLE `tab{self.doctype}` " + ", ".join(parts))


def _fake_frappe_modules(docfields, live_columns):
    _FrappeStyleTable.docfields = docfields
    _FrappeStyleTable.live_columns = live_columns
    _FrappeStyleTable.ddl_sink = []
    frappe = types.ModuleType("frappe")
    frappe.db = types.SimpleNamespace(
        sql_ddl=lambda q: _FrappeStyleTable.ddl_sink.append(q),
        table_exists=lambda dt: True,
    )
    frappe.get_meta = lambda dt: types.SimpleNamespace(issingle=0)
    database = types.ModuleType("frappe.database")
    maria = types.ModuleType("frappe.database.mariadb")
    maria_schema = types.ModuleType("frappe.database.mariadb.schema")
    maria_schema.MariaDBTable = _FrappeStyleTable
    schema = types.ModuleType("frappe.database.schema")
    schema.DbColumn = _FrappeStrictDbColumn
    return {
        "frappe": frappe,
        "frappe.database": database,
        "frappe.database.mariadb": maria,
        "frappe.database.mariadb.schema": maria_schema,
        "frappe.database.schema": schema,
    }


def _inspect(doctype, new_field, docfields, live_columns):
    with mock.patch.dict(sys.modules, _fake_frappe_modules(docfields, live_columns)):
        return inspect_frappe_ddl_plan(doctype, new_field)


def _core_table(money_type="decimal(21,9)", money_default="0.000000000"):
    docfields = [
        ("customer_name", "Data", None),
        ("total", "Currency", None),
        ("per_billed", "Percent", None),
        ("conversion_rate", "Float", None),
    ]
    live = [
        {"name": "customer_name", "type": "varchar(140)", "default": None},
        {"name": "total", "type": money_type, "default": money_default},
        {"name": "per_billed", "type": money_type, "default": money_default},
        {"name": "conversion_rate", "type": money_type, "default": money_default},
    ]
    return docfields, live


class TestFalseDecimalDriftIsSuppressed(unittest.TestCase):
    def test_stand_in_reproduces_the_phase0_phantom_without_the_gate_normalization(self) -> None:
        """Guard: the stand-in must emit the phantom MODIFY, or the tests below prove nothing."""
        docfields, live = _core_table()
        with mock.patch.dict(sys.modules, _fake_frappe_modules(docfields, live)):
            table = _FrappeStyleTable("Sales Order")
            table.setup_table_columns()
            table.alter()
        self.assertEqual(len(_FrappeStyleTable.ddl_sink), 1)
        self.assertIn("MODIFY `total` decimal(21,9) not null default 0", _FrappeStyleTable.ddl_sink[0])

    def test_custom_field_applies_on_each_core_doctype(self) -> None:
        docfields, live = _core_table()
        for doctype in CORE_DOCTYPES:
            for fieldtype, expected in (
                ("Currency", "decimal(21,9) not null default 0"),
                ("Float", "decimal(21,9) not null default 0"),
                ("Percent", "decimal(21,9) not null default 0"),
                ("Data", "varchar(140)"),
            ):
                with self.subTest(doctype=doctype, fieldtype=fieldtype):
                    result = _inspect(doctype, {"fieldname": "custom_x", "fieldtype": fieldtype}, docfields, live)
                    self.assertTrue(result.inspectable)
                    self.assertTrue(result.is_approved_additive_only, result.rejection_reason)
                    self.assertEqual(
                        result.statements,
                        [f"ALTER TABLE `tab{doctype}` ADD COLUMN `custom_x` {expected}"],
                    )

    def test_equivalent_live_type_spellings_are_not_drift(self) -> None:
        for spelling in ("DECIMAL(21,9)", "decimal(21, 9)", " decimal(21,9) "):
            for default in ("0.000000000", "'0.000000000'", "0", "0.0"):
                with self.subTest(spelling=spelling, default=default):
                    docfields, live = _core_table(money_type=spelling, money_default=default)
                    result = _inspect("Customer", {"fieldname": "custom_x", "fieldtype": "Currency"}, docfields, live)
                    self.assertTrue(result.is_approved_additive_only, result.statements)

    def test_rating_and_duration_zero_defaults_are_not_drift(self) -> None:
        docfields = [("score", "Rating", None), ("elapsed", "Duration", None)]
        live = [
            {"name": "score", "type": "decimal(3,2)", "default": "0.00"},
            {"name": "elapsed", "type": "decimal(21,9)", "default": "0.000000000"},
        ]
        result = _inspect("Item", {"fieldname": "custom_x", "fieldtype": "Data"}, docfields, live)
        self.assertTrue(result.is_approved_additive_only, result.statements)


class TestGenuineDecimalDriftIsStillFlagged(unittest.TestCase):
    def _assert_rejected_with_modify(self, docfields, live, doctype="Sales Invoice") -> None:
        result = _inspect(doctype, {"fieldname": "custom_x", "fieldtype": "Currency"}, docfields, live)
        self.assertTrue(result.inspectable)
        self.assertFalse(result.is_approved_additive_only)
        self.assertIn("MODIFY", result.rejection_reason or "")

    def test_precision_change_is_drift(self) -> None:
        docfields, live = _core_table()
        live[1]["type"] = "decimal(18,6)"
        self._assert_rejected_with_modify(docfields, live)

    def test_scale_change_is_drift(self) -> None:
        docfields, live = _core_table()
        live[1]["type"] = "decimal(21,2)"
        self._assert_rejected_with_modify(docfields, live)

    def test_different_type_is_drift(self) -> None:
        docfields, live = _core_table()
        live[1]["type"] = "varchar(140)"
        live[1]["default"] = None
        self._assert_rejected_with_modify(docfields, live)

    def test_unsigned_is_drift(self) -> None:
        docfields, live = _core_table()
        live[1]["type"] = "decimal(21,9) unsigned"
        self._assert_rejected_with_modify(docfields, live)

    def test_non_zero_live_default_is_drift(self) -> None:
        docfields, live = _core_table()
        live[1]["default"] = "5.000000000"
        self._assert_rejected_with_modify(docfields, live)

    def test_docfield_default_differing_from_live_default_is_drift(self) -> None:
        docfields, live = _core_table()
        docfields[1] = ("total", "Currency", "7")
        self._assert_rejected_with_modify(docfields, live)

    def test_unparseable_live_default_is_not_normalized_away(self) -> None:
        docfields, live = _core_table()
        live[1]["default"] = "abc"
        result = _inspect("Item", {"fieldname": "custom_x", "fieldtype": "Currency"}, docfields, live)
        self.assertFalse(result.is_approved_additive_only)

    def test_gate_still_rejects_any_modify_statement(self) -> None:
        ok, reason = validate_ddl_plan(
            ["ALTER TABLE `tabItem` ADD COLUMN `custom_x` decimal(21,9), MODIFY `total` decimal(21,9) not null default 0"]
        )
        self.assertFalse(ok)
        self.assertIn("MODIFY", reason or "")


class TestCanonicalColumnType(unittest.TestCase):
    def test_equivalent_spellings(self) -> None:
        self.assertEqual(_canonical_column_type("DECIMAL(21,9)"), "decimal(21,9)")
        self.assertEqual(_canonical_column_type("decimal(21, 9)"), "decimal(21,9)")
        self.assertEqual(_canonical_column_type("DECIMAL"), "decimal(10,0)")
        self.assertEqual(_canonical_column_type(None), "")

    def test_real_differences_stay_different(self) -> None:
        base = _canonical_column_type("decimal(21,9)")
        for other in ("decimal(18,9)", "decimal(21,6)", "decimal(21,9) unsigned", "double", "varchar(21)"):
            self.assertNotEqual(base, _canonical_column_type(other), other)


class TestSimulatorTypeComparison(unittest.TestCase):
    def _plan(self, live_type: str):
        sim = SimulatedMariaDBTable("Sales Order")
        sim.current_columns = {
            "name": ColumnDesc(name="name", type="varchar(140)"),
            "total": ColumnDesc(name="total", type=live_type),
        }
        sim.columns["total"] = SimulatedDbColumn(sim, "total", "Currency")
        sim.columns["custom_probe"] = SimulatedDbColumn(sim, "custom_probe", "Data")
        return sim.alter()

    def test_equivalent_type_spelling_is_not_drift(self) -> None:
        for spelling in ("DECIMAL(21,9)", "decimal(21, 9)"):
            with self.subTest(spelling=spelling):
                ok, reason = validate_ddl_plan(self._plan(spelling))
                self.assertTrue(ok, reason)

    def test_real_type_change_is_drift(self) -> None:
        for live_type in ("decimal(18,6)", "decimal(21,2)", "decimal(21,9) unsigned", "double"):
            with self.subTest(live_type=live_type):
                ok, reason = validate_ddl_plan(self._plan(live_type))
                self.assertFalse(ok)
                self.assertIn("MODIFY", reason or "")


class TestFrappePathHelper(unittest.TestCase):
    def test_helper_returns_only_the_add_column_statement(self) -> None:
        docfields, live = _core_table()
        with mock.patch.dict(sys.modules, _fake_frappe_modules(docfields, live)):
            statements = _inspect_with_frappe_mariadb_table("Customer", {"fieldname": "custom_x", "fieldtype": "Currency"})
        self.assertEqual(statements, ["ALTER TABLE `tabCustomer` ADD COLUMN `custom_x` decimal(21,9) not null default 0"])


if __name__ == "__main__":
    unittest.main()
