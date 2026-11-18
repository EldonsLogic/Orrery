"""ERP-027 tests: no false MODIFY COLUMN drift on decimal(21,9) columns in the DDL plan gate.

Phase 0 finding (E0-7 #1): MariaDB reports `COLUMN_DEFAULT = '0.000000000'` for decimal(21,9)
columns that Frappe DocFields declare with no default, so Frappe's `MariaDBTable.alter()` emits
phantom `MODIFY ... decimal(21,9) not null default 0` statements and the gate rejects every
customer-added field on Customer, Sales Order, Sales Invoice and Item.

These tests drive the Frappe-native inspection path (`_inspect_with_frappe_mariadb_table`)
against a small in-process stand-in for Frappe's `MariaDBTable` / `DbColumn` that copies the
comparison logic of Frappe v15 (strict string type compare, `default_changed_for_decimal`),
so the real code path is exercised without a bench. A live-bench run of the same checks is in
the ERP-027 log. Genuine type, precision, scale, default and nullability changes must still be
flagged, and the gate must REJECT (never approve) when the Frappe inspection cannot run.

Stand-in limits (review ERP-027 L-notes): it copies v15 type and default comparison, but omits
the ``DEFAULT_SHORTCUTS`` / ``:``-prefix branch of ``DbColumn.get_definition`` and uses the
simulator's ``get_definition`` for the generated side.
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

from change_engine.api.endpoints import FrappeDeploymentAdapter  # noqa: E402
from change_engine.guarded_apply.ddl_plan_gate import (  # noqa: E402
    MARIADB_TYPE_MAP,
    REASON_EXISTING_COLUMNS_MISSING,
    REASON_FRAPPE_IMPORT_FAILED,
    REASON_FRAPPE_UNAVAILABLE,
    REASON_INSPECTION_FAILED,
    ColumnDesc,
    FrappeInspectionError,
    SimulatedDbColumn,
    SimulatedMariaDBTable,
    _canonical_column_type,
    _col_with,
    _inspect_with_frappe_mariadb_table,
    assess_applied_ddl,
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


def _fake_frappe_modules(docfields, live_columns, *, db_connected=True, with_dbcolumn=True):
    _FrappeStyleTable.docfields = docfields
    _FrappeStyleTable.live_columns = live_columns
    _FrappeStyleTable.ddl_sink = []
    frappe = types.ModuleType("frappe")
    frappe.db = (
        types.SimpleNamespace(
            sql_ddl=lambda q: _FrappeStyleTable.ddl_sink.append(q),
            table_exists=lambda dt: True,
        )
        if db_connected
        else None
    )
    frappe.get_meta = lambda dt: types.SimpleNamespace(issingle=0)
    database = types.ModuleType("frappe.database")
    maria = types.ModuleType("frappe.database.mariadb")
    maria_schema = types.ModuleType("frappe.database.mariadb.schema")
    maria_schema.MariaDBTable = _FrappeStyleTable
    schema = types.ModuleType("frappe.database.schema")
    if with_dbcolumn:
        schema.DbColumn = _FrappeStrictDbColumn
    return {
        "frappe": frappe,
        "frappe.database": database,
        "frappe.database.mariadb": maria,
        "frappe.database.mariadb.schema": maria_schema,
        "frappe.database.schema": schema,
    }


def _inspect(doctype, new_field, docfields, live_columns, *, existing=True, **module_opts):
    """Live-mode call (offline_simulator off). The live caller supplies the column read."""
    desc = [ColumnDesc(**c) for c in live_columns] if existing else None
    with mock.patch.dict(sys.modules, _fake_frappe_modules(docfields, live_columns, **module_opts)):
        return inspect_frappe_ddl_plan(doctype, new_field, existing_columns_desc=desc)


def _core_table(money_type="decimal(21,9)", money_default="0.000000000"):
    docfields = [
        ("customer_name", "Data", None),
        ("total", "Currency", None),
        ("per_billed", "Percent", None),
        ("conversion_rate", "Float", None),
    ]
    live = [
        {"name": "customer_name", "type": "varchar(140)", "default": None, "nullable": True},
        {"name": "total", "type": money_type, "default": money_default, "nullable": False},
        {"name": "per_billed", "type": money_type, "default": money_default, "nullable": False},
        {"name": "conversion_rate", "type": money_type, "default": money_default, "nullable": False},
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
        self.assertEqual(_canonical_column_type(None), "")

    def test_real_differences_stay_different(self) -> None:
        base = _canonical_column_type("decimal(21,9)")
        others = (
            "decimal(18,9)", "decimal(21,6)", "decimal(21,9) unsigned", "decimal(21,9) zerofill",
            "numeric(21,9)", "dec(21,9)", "decimal", "double", "varchar(21)",
        )
        for other in others:
            self.assertNotEqual(base, _canonical_column_type(other), other)

    def test_no_synonym_policy_bare_decimal_is_not_rewritten(self) -> None:
        for bare in ("decimal", "numeric", "dec"):
            self.assertEqual(_canonical_column_type(bare), bare)

    def test_quoted_literals_are_not_rewritten(self) -> None:
        self.assertEqual(_canonical_column_type("ENUM('A B','C')"), "enum('A B','C')")

    def test_generated_side_is_already_canonical(self) -> None:
        for fieldtype, (name, args) in MARIADB_TYPE_MAP.items():
            generated = f"{name}({args})" if args else name
            self.assertEqual(_canonical_column_type(generated), generated, fieldtype)


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
            statements = _inspect_with_frappe_mariadb_table(
                "Customer",
                {"fieldname": "custom_x", "fieldtype": "Currency"},
                existing_columns_desc=[ColumnDesc(**c) for c in live],
            )
        self.assertEqual(statements, ["ALTER TABLE `tabCustomer` ADD COLUMN `custom_x` decimal(21,9) not null default 0"])


_ALL_MODIFY_LIVE_FIELD = {"fieldname": "custom_x", "fieldtype": "Data"}


class TestRatingAndDurationAreNotNormalized(unittest.TestCase):
    """H1: only Currency/Float/Percent get `not null default 0` in Frappe v15 (schema.py:201)."""

    def test_rating_and_duration_zero_live_default_is_rejected(self) -> None:
        for ftype, ctype, cdefault in (
            ("Rating", "decimal(3,2)", "0.00"),
            ("Duration", "decimal(21,9)", "0.000000000"),
        ):
            with self.subTest(fieldtype=ftype):
                docfields = [("f", ftype, None)]
                live = [{"name": "f", "type": ctype, "default": cdefault, "nullable": False}]
                result = _inspect("Item", _ALL_MODIFY_LIVE_FIELD, docfields, live)
                self.assertTrue(result.inspectable)
                self.assertFalse(result.is_approved_additive_only)
                self.assertIn("MODIFY", result.rejection_reason or "")

    def test_rating_and_duration_with_null_default_are_not_drift(self) -> None:
        docfields = [("score", "Rating", None), ("elapsed", "Duration", None)]
        live = [
            {"name": "score", "type": "decimal(3,2)", "default": None, "nullable": True},
            {"name": "elapsed", "type": "decimal(21,9)", "default": None, "nullable": True},
        ]
        result = _inspect("Item", _ALL_MODIFY_LIVE_FIELD, docfields, live)
        self.assertTrue(result.is_approved_additive_only, result.statements)


class TestNullabilityIsNotHidden(unittest.TestCase):
    """M1: Frappe's phantom MODIFY is `not null default 0`; on a nullable column it is real."""

    def _total(self, nullable):
        docfields, live = _core_table()
        live[1]["nullable"] = nullable
        return _inspect("Customer", {"fieldname": "custom_x", "fieldtype": "Currency"}, docfields, live)

    def test_nullable_column_with_zero_default_is_rejected(self) -> None:
        result = self._total(True)
        self.assertFalse(result.is_approved_additive_only)
        self.assertIn("MODIFY", result.rejection_reason or "")

    def test_unknown_nullability_is_rejected_fail_closed(self) -> None:
        result = self._total(None)
        self.assertFalse(result.is_approved_additive_only)

    def test_not_null_column_with_zero_default_is_not_drift(self) -> None:
        self.assertTrue(self._total(False).is_approved_additive_only)


class TestFailClosedWhenFrappeInspectionCannotRun(unittest.TestCase):
    """H2: never fall back to the simulator on a live call; reject with a coded reason."""

    FIELD = {"fieldname": "custom_x", "fieldtype": "Currency"}

    def _assert_rejected(self, result, code) -> None:
        self.assertFalse(result.inspectable)
        self.assertFalse(result.is_approved_additive_only)
        self.assertEqual(result.reason_code, code)
        self.assertIn(code, result.rejection_reason or "")
        self.assertEqual(result.statements, [])

    def test_inspection_raising_is_rejected(self) -> None:
        docfields, live = _core_table(money_type="decimal(18,2)")
        modules = _fake_frappe_modules(docfields, live)

        class _Boom(_FrappeStyleTable):
            def alter(self):
                raise RuntimeError("boom")

        modules["frappe.database.mariadb.schema"].MariaDBTable = _Boom
        with mock.patch.dict(sys.modules, modules):
            result = inspect_frappe_ddl_plan(
                "Sales Order", self.FIELD, existing_columns_desc=[ColumnDesc(**c) for c in live]
            )
        self._assert_rejected(result, REASON_INSPECTION_FAILED)

    def test_constructor_signature_change_is_rejected(self) -> None:
        """A Frappe upgrade that changes DbColumn kwargs must not become a rubber stamp."""
        docfields, live = _core_table(money_type="decimal(18,2)")
        modules = _fake_frappe_modules(docfields, live)

        class _NewSignature:
            def __init__(self, table, name):  # old kwargs no longer accepted
                pass

        modules["frappe.database.schema"].DbColumn = _NewSignature
        with mock.patch.dict(sys.modules, modules):
            result = inspect_frappe_ddl_plan(
                "Sales Order", self.FIELD, existing_columns_desc=[ColumnDesc(**c) for c in live]
            )
        self._assert_rejected(result, REASON_INSPECTION_FAILED)

    def test_dbcolumn_import_failure_is_rejected(self) -> None:
        docfields, live = _core_table(money_type="decimal(18,2)")
        result = _inspect("Sales Order", self.FIELD, docfields, live, with_dbcolumn=False)
        self._assert_rejected(result, REASON_FRAPPE_IMPORT_FAILED)

    def test_decimal_drift_without_existing_definitions_is_rejected(self) -> None:
        docfields, live = _core_table(money_type="decimal(18,2)")
        result = _inspect("Sales Order", self.FIELD, docfields, live, existing=False)
        self._assert_rejected(result, REASON_EXISTING_COLUMNS_MISSING)

    def test_frappe_db_not_connected_is_rejected(self) -> None:
        docfields, live = _core_table()
        result = _inspect("Sales Order", self.FIELD, docfields, live, db_connected=False)
        self._assert_rejected(result, REASON_FRAPPE_UNAVAILABLE)

    def test_frappe_not_importable_is_rejected_not_simulated(self) -> None:
        blocked = {name: None for name in ("frappe", "frappe.database", "frappe.database.mariadb")}
        with mock.patch.dict(sys.modules, blocked):
            result = inspect_frappe_ddl_plan(
                "Sales Order",
                {"fieldname": "custom_x", "fieldtype": "Data"},
                existing_columns_desc=[ColumnDesc(name="name", type="varchar(140)")],
            )
        self._assert_rejected(result, REASON_FRAPPE_UNAVAILABLE)

    def test_helper_raises_coded_error(self) -> None:
        with mock.patch.dict(sys.modules, {"frappe": None}):
            with self.assertRaises(FrappeInspectionError) as ctx:
                _inspect_with_frappe_mariadb_table("Item", {"fieldname": "custom_x"}, existing_columns_desc=[])
        self.assertEqual(ctx.exception.code, REASON_FRAPPE_UNAVAILABLE)

    def test_simulator_only_with_explicit_offline_flag(self) -> None:
        field = {"fieldname": "custom_x", "fieldtype": "Data"}
        cols = [ColumnDesc(name="name", type="varchar(140)")]
        offline = inspect_frappe_ddl_plan("Item", field, existing_columns_desc=cols, offline_simulator=True)
        self.assertTrue(offline.is_approved_additive_only)
        default = inspect_frappe_ddl_plan("Item", field, existing_columns_desc=cols)
        self.assertFalse(default.is_approved_additive_only)

    def test_upper_case_real_type_change_still_rejected_on_frappe_path(self) -> None:
        docfields, live = _core_table(money_type="DECIMAL(18,6)")
        result = _inspect("Sales Order", self.FIELD, docfields, live)
        self.assertFalse(result.is_approved_additive_only)
        self.assertIn("MODIFY", result.rejection_reason or "")


class TestColumnCopyKeepsExtraKeys(unittest.TestCase):
    """L2: copying a live column description must not drop keys a newer Frappe adds."""

    def test_extra_keys_survive(self) -> None:
        col = {"name": "total", "type": "DECIMAL(21,9)", "default": "0", "index": 0, "unique": 0, "collation": "x"}
        copy = _col_with(col, type="decimal(21,9)")
        self.assertEqual(copy["collation"], "x")
        self.assertEqual(copy["type"], "decimal(21,9)")
        self.assertEqual(col["type"], "DECIMAL(21,9)")


_T = "ALTER TABLE `tabItem` "
_ADD = "ADD COLUMN `custom_x` varchar(140)"
_SCHEMA = {
    "columns": {"name": ("varchar(140)", "NO", "None", "PRI"), "total": ("decimal(21,9)", "NO", "0.000000000", "")},
    "indexes": {("PRIMARY", "name", "0", "1")},
}


def _after(**changes):
    cols = dict(_SCHEMA["columns"])
    cols["custom_x"] = ("varchar(140)", "YES", "None", "")
    idx = set(_SCHEMA["indexes"])
    cols.update(changes.pop("cols", {}))
    idx |= changes.pop("add_idx", set())
    return {"columns": cols, "indexes": idx}


class TestAssessAppliedDdl(unittest.TestCase):
    """H1/M1: the statements that actually ran are compared with the approved plan."""

    def assess(self, executed, after=None, approved=None):
        return assess_applied_ddl(
            "Item", "custom_x", approved if approved is not None else [_T + _ADD],
            executed, _SCHEMA, after if after is not None else _after(),
        )

    def test_executed_equals_approved(self) -> None:
        self.assertEqual(self.assess([_T + _ADD]), (False, None))

    def test_phantom_noop_modify_tolerated_only_when_schema_unchanged(self) -> None:
        executed = [_T + _ADD + ", MODIFY `total` decimal(21,9) not null default 0"]
        self.assertEqual(self.assess(executed), (False, None))

    def test_modify_that_changes_an_existing_column_is_a_side_effect(self) -> None:
        executed = [_T + _ADD + ", MODIFY `total` decimal(21,9)"]
        after = _after(cols={"total": ("decimal(21,9)", "YES", "None", "")})
        unapproved, why = self.assess(executed, after)
        self.assertTrue(unapproved)
        self.assertIn("total", why)

    def test_index_change_is_a_side_effect(self) -> None:
        unapproved, _ = self.assess([_T + _ADD], _after(add_idx={("idx_x", "total", "1", "1")}))
        self.assertTrue(unapproved)

    def test_other_clause_kinds_are_side_effects(self) -> None:
        for extra in ("DROP COLUMN `total`", "ADD INDEX `i` (`total`)", "ADD UNIQUE `u` (`total`)"):
            with self.subTest(extra=extra):
                self.assertTrue(self.assess([_T + _ADD + ", " + extra])[0])

    def test_other_table_or_other_ddl_is_a_side_effect(self) -> None:
        self.assertTrue(self.assess([_T + _ADD, "ALTER TABLE `tabCustomer` ADD COLUMN `a` int"])[0])
        self.assertTrue(self.assess([_T + _ADD, "CREATE INDEX i ON `tabItem` (`total`)"])[0])

    def test_different_add_column_than_approved_is_a_side_effect(self) -> None:
        self.assertTrue(self.assess([_T + "ADD COLUMN `custom_x` text"])[0])
        self.assertTrue(self.assess([_T + _ADD + ", ADD COLUMN `custom_y` int"])[0])

    def test_unknown_inputs_fail_closed(self) -> None:
        self.assertTrue(assess_applied_ddl("Item", "custom_x", None, [_T + _ADD], _SCHEMA, _after())[0])
        self.assertTrue(assess_applied_ddl("Item", "custom_x", [_T + _ADD], None, _SCHEMA, _after())[0])
        self.assertTrue(assess_applied_ddl("Item", "custom_x", [_T + _ADD], [_T + _ADD], None, _after())[0])

    def test_clean_failure_nothing_ran_nothing_changed(self) -> None:
        self.assertEqual(assess_applied_ddl("Item", "custom_x", [_T + _ADD], [], _SCHEMA, _SCHEMA), (False, None))

    def test_ran_nothing_recorded_but_schema_changed_is_a_side_effect(self) -> None:
        self.assertTrue(assess_applied_ddl("Item", "custom_x", [_T + _ADD], [], _SCHEMA, _after())[0])


class _LiveDb:
    """Minimal live-mode frappe.db double for the adapter's after-snapshot."""

    def __init__(self, executed_plan, after_changes=None):
        self.executed_plan = executed_plan
        self.after_changes = after_changes or {}
        self.inserted = False
        self.ddl_log = []

    def sql(self, query, values=None):
        q = " ".join(query.upper().split())
        if "FROM `TABCUSTOM FIELD`" in q:
            return (("Item-custom_x", "Data"),) if self.inserted else ()
        if "FROM INFORMATION_SCHEMA.STATISTICS" in q:
            return tuple(self._schema()["indexes"])
        if "SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT, COLUMN_KEY" in q:
            return tuple((n, *d) for n, d in self._schema()["columns"].items())
        if "COLUMN_NAME = %S" in q:
            return (("custom_x", "varchar(140)"),) if self.inserted else ()
        if "SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT" in q:
            return ()
        return ()

    def _schema(self):
        return _after(**{"cols": self.after_changes}) if self.inserted else _SCHEMA

    def sql_ddl(self, query):
        self.ddl_log.append(query)

    def commit(self):
        pass


class TestAdapterAfterSnapshotIsNotHardCoded(unittest.TestCase):
    def _run(self, executed, after_changes=None):
        db = _LiveDb(executed, after_changes)
        module = types.SimpleNamespace(db=db, clear_cache=lambda **kw: None)

        def get_doc(args):
            def insert(ignore_permissions=True):
                for stmt in executed:
                    module.db.sql_ddl(stmt)  # goes through the adapter's recording wrapper
                db.inserted = True

            return types.SimpleNamespace(insert=insert)

        module.get_doc = get_doc
        adapter = FrappeDeploymentAdapter(frappe_module=module, in_memory=False)
        before = adapter.take_snapshot("Item", "custom_x", "dep1")
        adapter._approved_ddl["dep1"] = [_T + _ADD]
        adapter.apply_native_custom_field("dep1", "Item", {"fieldname": "custom_x", "fieldtype": "Data"})
        after = adapter.take_snapshot("Item", "custom_x", "dep1")
        return before, after, db

    def test_approved_statement_only_is_clean(self) -> None:
        _, after, db = self._run([_T + _ADD])
        self.assertFalse(after.unapproved_side_effects)
        self.assertTrue(after.indexes_unchanged)
        self.assertEqual(db.ddl_log, [_T + _ADD], "recorded statements are still executed")

    def test_unplanned_statement_is_an_unapproved_side_effect(self) -> None:
        _, after, _ = self._run([_T + _ADD, "ALTER TABLE `tabItem` DROP COLUMN `total`"])
        self.assertTrue(after.unapproved_side_effects)

    def test_executed_modify_that_changed_a_column_is_an_unapproved_side_effect(self) -> None:
        executed = [_T + _ADD + ", MODIFY `total` decimal(21,9)"]
        _, after, _ = self._run(executed, {"total": ("decimal(21,9)", "YES", "None", "")})
        self.assertTrue(after.unapproved_side_effects)

    def test_missing_approved_plan_fails_closed(self) -> None:
        db = _LiveDb([])
        module = types.SimpleNamespace(db=db, clear_cache=lambda **kw: None)
        adapter = FrappeDeploymentAdapter(frappe_module=module, in_memory=False)
        adapter.take_snapshot("Item", "custom_x", "dep1")
        adapter.apply_called = True
        after = adapter.take_snapshot("Item", "custom_x", "dep1")
        self.assertTrue(after.unapproved_side_effects)


if __name__ == "__main__":
    unittest.main()
