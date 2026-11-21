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

from change_engine.api import endpoints  # noqa: E402
from change_engine.api.endpoints import FrappeDeploymentAdapter, RevisionHashError  # noqa: E402
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
    _normalize_sql,
    _split_alter_clauses,
    assess_applied_ddl,
    inspect_frappe_ddl_plan,
    new_column_matches_plan,
    noop_modify_allowlist,
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
_PHANTOM = "MODIFY `total` decimal(21,9) not null default 0"


def _col(type_="varchar(140)", nullable="YES", default="None", key="", charset="utf8mb4",
         collation="utf8mb4_unicode_ci", extra="", comment="", generation="None"):
    return {"type": type_, "nullable": nullable, "default": default, "key": key, "charset": charset,
            "collation": collation, "extra": extra, "comment": comment, "generation": generation}


def _before():
    cols = {
        "name": _col(nullable="NO", key="PRI"),
        "total": _col("decimal(21,9)", "NO", "0.000000000", charset="None", collation="None"),
        "note": _col(),
    }
    return {
        "columns": cols,
        "order": list(cols),
        "indexes": {("PRIMARY", "name", "0", "1", "None", "BTREE")},
        "constraints": {("PRIMARY", "PRIMARY KEY")},
        "checks": set(),
        "triggers": set(),
        "table": ("InnoDB", "utf8mb4_unicode_ci", "Dynamic"),
    }


def _after(mutate=None, *, field="custom_x", field_col=None):
    schema = _before()
    schema["columns"][field] = field_col or _col()
    schema["order"].append(field)
    if mutate:
        mutate(schema)
    return schema


class TestQuoteAwareSplitter(unittest.TestCase):
    """Re-review H1 (3): a quoted ``(`` or backtick must never hide a trailing clause."""

    def test_quoted_paren_does_not_keep_trailing_clauses_attached(self) -> None:
        stmt = _T + "MODIFY `note` varchar(140) default ':(', ADD CONSTRAINT c CHECK (a > 1), FORCE"
        table, clauses = _split_alter_clauses(stmt)
        self.assertEqual(table, "`tabItem`")
        self.assertEqual(clauses, ["MODIFY `note` varchar(140) default ':('", "ADD CONSTRAINT c CHECK (a > 1)", "FORCE"])

    def test_close_paren_in_literal_and_backtick_identifier(self) -> None:
        _, clauses = _split_alter_clauses(_T + "MODIFY `a)b` int default ')', DROP FOREIGN KEY `f(1`")
        self.assertEqual(clauses, ["MODIFY `a)b` int default ')'", "DROP FOREIGN KEY `f(1`"])

    def test_commas_inside_literals_and_decimals_do_not_split(self) -> None:
        _, clauses = _split_alter_clauses(_T + "ADD COLUMN `c` decimal(21,9) default 'a,b', MODIFY `d` int")
        self.assertEqual(len(clauses), 2)

    def test_escaped_and_doubled_quotes(self) -> None:
        stmt = _T + "MODIFY `n` varchar(9) default 'it\\'s (', MODIFY `m` varchar(9) default 'a''(', FORCE"
        _, clauses = _split_alter_clauses(stmt)
        self.assertEqual(len(clauses), 3)

    def test_unparseable_statements_raise(self) -> None:
        for bad in (
            "MODIFY `n` int /*! , DROP COLUMN `total` */",
            "MODIFY `n` int -- , DROP COLUMN total",
            "MODIFY `n` int # x",
            "MODIFY `n` int; DROP TABLE `tabItem`",
            "MODIFY `n` varchar(9) default 'unterminated",
            "MODIFY `n` int ((",
            "MODIFY `n` int )",
        ):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    _split_alter_clauses(_T + bad)

    def test_not_an_alter_table_is_empty(self) -> None:
        self.assertEqual(_split_alter_clauses("DROP TABLE `tabItem`"), ("", []))

    def test_normalisation_keeps_literals_and_identifiers_verbatim(self) -> None:
        a = _normalize_sql("MODIFY  `Total`  DECIMAL(21, 9)  NOT NULL  DEFAULT 0")
        self.assertEqual(a, _normalize_sql("modify `Total` decimal(21,9) not null default 0"))
        self.assertNotEqual(_normalize_sql("MODIFY `a` varchar(9) default 'X'"), _normalize_sql("MODIFY `a` varchar(9) default 'x'"))
        self.assertNotEqual(_normalize_sql("MODIFY `A` int"), _normalize_sql("MODIFY `a` int"))


class TestNoopModifyAllowList(unittest.TestCase):
    """Re-review H1: the allow-list is regenerated deterministically from the BEFORE snapshot."""

    def test_zero_default_not_null_decimal_has_exactly_the_phantom_clause(self) -> None:
        allowed = noop_modify_allowlist(_before())
        self.assertEqual(allowed, {"total": {_normalize_sql(_PHANTOM)}})

    def test_nullable_or_non_zero_default_decimals_are_not_listed(self) -> None:
        for nullable, default in (("YES", "0.000000000"), ("NO", "5.000000000"), ("NO", "None")):
            with self.subTest(nullable=nullable, default=default):
                before = _before()
                before["columns"]["total"] = _col("decimal(21,9)", nullable, default)
                self.assertEqual(noop_modify_allowlist(before), {})

    def test_non_canonical_type_spelling_lists_the_restatement_only(self) -> None:
        before = _before()
        before["columns"]["note"] = _col("VARCHAR(140)", "NO", "'x'")
        allowed = noop_modify_allowlist(before)
        self.assertEqual(allowed["note"], {_normalize_sql("MODIFY `note` varchar(140) not null default 'x'")})

    def test_generation_is_deterministic(self) -> None:
        self.assertEqual(noop_modify_allowlist(_before()), noop_modify_allowlist(_before()))


class TestAssessAppliedDdl(unittest.TestCase):
    """Re-review H1/M1: what ran is compared with the approved plan and the allow-list."""

    def assess(self, executed, after=None, approved=None, before=None):
        return assess_applied_ddl(
            "Item", "custom_x", approved if approved is not None else [_T + _ADD], executed,
            before if before is not None else _before(), after if after is not None else _after(),
        )

    def assertRejected(self, result, needle=None):
        self.assertTrue(result[0], f"expected an unapproved side effect, got {result}")
        if needle:
            self.assertIn(needle, result[1])

    # normal cases ---------------------------------------------------------------------
    def test_executed_equals_approved(self) -> None:
        self.assertEqual(self.assess([_T + _ADD]), (False, None))

    def test_phantom_noop_modify_from_the_allow_list_passes(self) -> None:
        self.assertEqual(self.assess([_T + _ADD + ", " + _PHANTOM]), (False, None))

    def test_phantom_modify_in_a_separate_statement_or_other_spelling_passes(self) -> None:
        self.assertEqual(self.assess([_T + _ADD, _T + _PHANTOM]), (False, None))
        spelled = _T + "ADD  COLUMN `custom_x` VARCHAR(140),  MODIFY `total`  DECIMAL(21, 9) NOT NULL DEFAULT 0"
        self.assertEqual(self.assess([spelled]), (False, None))

    def test_clean_failure_nothing_ran_nothing_changed(self) -> None:
        self.assertEqual(self.assess([], after=_before()), (False, None))

    def test_json_field_with_its_own_json_valid_check_passes(self) -> None:
        def mutate(s):
            s["checks"].add(("custom_x", "json_valid(`custom_x`)"))
            s["constraints"].add(("custom_x", "CHECK"))

        after = _after(mutate, field_col=_col("longtext", collation="utf8mb4_bin"))
        add = "ADD COLUMN `custom_x` json"
        self.assertEqual(self.assess([_T + add], after, approved=[_T + add]), (False, None))

    def test_json_allowance_does_not_cover_a_different_check(self) -> None:
        def mutate(s):
            s["checks"].add(("evil", "`total` > 0"))
            s["constraints"].add(("evil", "CHECK"))

        add = "ADD COLUMN `custom_x` json"
        self.assertRejected(self.assess([_T + add], _after(mutate), approved=[_T + add]), "changed during apply")

    # re-review bypass 1: properties invisible to the old 4-tuple -----------------------
    def test_modify_that_changes_charset_is_rejected(self) -> None:
        def mutate(s):
            s["columns"]["note"] = _col(charset="latin1", collation="latin1_swedish_ci")

        executed = [_T + _ADD + ", MODIFY `note` varchar(140) CHARACTER SET latin1"]
        self.assertRejected(self.assess(executed, _after(mutate)), "not in the allow-list")

    def test_modify_with_collate_extra_first_after_check_comment_is_rejected(self) -> None:
        for suffix in (
            " COLLATE utf8mb4_bin", " AUTO_INCREMENT", " ON UPDATE CURRENT_TIMESTAMP", " FIRST",
            " AFTER `name`", " CHECK (`total` > 0)", " COMMENT 'x'", " unique",
        ):
            with self.subTest(suffix=suffix):
                executed = [_T + _ADD + ", " + _PHANTOM + suffix]
                self.assertRejected(self.assess(executed), "not in the allow-list")

    def test_fingerprint_detects_a_change_to_every_column_attribute(self) -> None:
        for attr, value in (
            ("type", "decimal(18,2)"), ("nullable", "YES"), ("default", "5"), ("key", "MUL"),
            ("charset", "latin1"), ("collation", "latin1_bin"), ("extra", "on update current_timestamp()"),
            ("comment", "x"), ("generation", "total * 2"),
        ):
            with self.subTest(attr=attr):
                def mutate(s, attr=attr, value=value):
                    s["columns"]["total"][attr] = value

                self.assertRejected(self.assess([_T + _ADD], _after(mutate)), "total")

    def test_fingerprint_detects_column_order_change(self) -> None:
        def mutate(s):
            s["order"] = ["total", "name", "note", "custom_x"]

        self.assertRejected(self.assess([_T + _ADD], _after(mutate)), "order")

    def test_fingerprint_detects_check_constraint_trigger_index_table_changes(self) -> None:
        mutations = {
            "check": lambda s: s["checks"].add(("c", "`total` > 0")),
            "constraint": lambda s: s["constraints"].add(("fk", "FOREIGN KEY")),
            "constraint dropped": lambda s: s["constraints"].clear(),
            "trigger": lambda s: s["triggers"].add(("t", "INSERT", "BEFORE", "h")),
            "index": lambda s: s["indexes"].add(("i", "total", "1", "1", "None", "BTREE")),
            "index dropped": lambda s: s["indexes"].clear(),
            "engine": lambda s: s.update(table=("MyISAM", "utf8mb4_unicode_ci", "Dynamic")),
            "table collation": lambda s: s.update(table=("InnoDB", "latin1_swedish_ci", "Dynamic")),
            "row format": lambda s: s.update(table=("InnoDB", "utf8mb4_unicode_ci", "Compact")),
            "column dropped": lambda s: (s["columns"].pop("note"), s["order"].remove("note")),
            "second column added": lambda s: (s["columns"].update(extra=_col()), s["order"].append("extra")),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                self.assertRejected(self.assess([_T + _ADD], _after(mutate)))

    # re-review bypass 2: lossy MODIFY then restore -------------------------------------
    def test_shrink_then_restore_in_one_statement_is_rejected(self) -> None:
        executed = [_T + _ADD + ", MODIFY `total` decimal(10,0), " + _PHANTOM]
        self.assertRejected(self.assess(executed), "not in the allow-list")

    def test_shrink_then_restore_across_two_statements_is_rejected(self) -> None:
        executed = [_T + _ADD, _T + "MODIFY `total` decimal(10,0)", _T + _PHANTOM]
        self.assertRejected(self.assess(executed), "not in the allow-list")

    def test_nullability_and_charset_round_trips_are_rejected(self) -> None:
        for lossy in (
            "MODIFY `note` varchar(140) not null default ''",
            "MODIFY `note` varchar(140) CHARACTER SET ascii",
            "MODIFY `note` varchar(140)",  # a no-op restatement that is not in the allow-list
        ):
            with self.subTest(lossy=lossy):
                self.assertRejected(self.assess([_T + _ADD, _T + lossy, _T + "MODIFY `note` varchar(140)"]))

    def test_the_same_allow_listed_modify_twice_is_rejected(self) -> None:
        self.assertRejected(self.assess([_T + _ADD + ", " + _PHANTOM + ", " + _PHANTOM]), "more than once")
        self.assertRejected(self.assess([_T + _ADD + ", " + _PHANTOM, _T + _PHANTOM]), "more than once")

    def test_modify_not_in_the_allow_list_is_rejected_even_when_the_schema_is_unchanged(self) -> None:
        # the previous rule tolerated every MODIFY whose before/after fingerprint matched
        self.assertRejected(self.assess([_T + _ADD + ", MODIFY `total` decimal(21,9)"]), "not in the allow-list")
        self.assertRejected(self.assess([_T + _ADD + ", MODIFY `note` varchar(140)"]), "not in the allow-list")

    def test_phantom_modify_on_a_nullable_decimal_is_rejected(self) -> None:
        before = _before()
        before["columns"]["total"]["nullable"] = "YES"
        after = _after()
        after["columns"]["total"]["nullable"] = "YES"
        self.assertRejected(self.assess([_T + _ADD + ", " + _PHANTOM], after, before=before), "not in the allow-list")

    # re-review bypass 3: quote-blind splitting -----------------------------------------
    def test_trailing_clause_smuggled_after_a_quoted_paren_is_rejected(self) -> None:
        for smuggled in (
            "ADD CONSTRAINT chk CHECK (`total` > 0)", "DROP FOREIGN KEY `f`", "ENGINE=MyISAM", "FORCE",
            "CONVERT TO CHARACTER SET latin1",
        ):
            with self.subTest(smuggled=smuggled):
                executed = [_T + _ADD + ", MODIFY `note` varchar(140) default ':(', " + smuggled]
                self.assertRejected(self.assess(executed))

    def test_comment_separator_and_unterminated_quote_statements_fail_closed(self) -> None:
        for tail in ("/*! , ENGINE=MyISAM */", "-- , FORCE", "; DROP TABLE `tabItem`", " default 'x"):
            with self.subTest(tail=tail):
                self.assertRejected(self.assess([_T + _ADD + ", " + _PHANTOM + tail]), "parsed")

    # other clause kinds, tables and unknown input --------------------------------------
    def test_other_clause_kinds_are_side_effects(self) -> None:
        for extra in ("DROP COLUMN `total`", "ADD INDEX `i` (`total`)", "ADD UNIQUE `u` (`total`)"):
            with self.subTest(extra=extra):
                self.assertRejected(self.assess([_T + _ADD + ", " + extra]))

    def test_other_table_or_other_ddl_is_a_side_effect(self) -> None:
        self.assertRejected(self.assess([_T + _ADD, "ALTER TABLE `tabCustomer` ADD COLUMN `a` int"]))
        self.assertRejected(self.assess([_T + _ADD, "CREATE INDEX i ON `tabItem` (`total`)"]))

    def test_different_add_column_than_approved_is_a_side_effect(self) -> None:
        self.assertRejected(self.assess([_T + "ADD COLUMN `custom_x` text"]))
        self.assertRejected(self.assess([_T + _ADD + ", ADD COLUMN `custom_y` int"]))

    def test_unknown_or_incomplete_inputs_fail_closed(self) -> None:
        b, a = _before(), _after()
        self.assertRejected(assess_applied_ddl("Item", "custom_x", None, [_T + _ADD], b, a))
        self.assertRejected(assess_applied_ddl("Item", "custom_x", [_T + _ADD], None, b, a))
        self.assertRejected(assess_applied_ddl("Item", "custom_x", [_T + _ADD], [_T + _ADD], None, a))
        old_shape = {"columns": {"name": ("varchar(140)", "NO", "None", "PRI")}, "indexes": set()}
        self.assertRejected(assess_applied_ddl("Item", "custom_x", [_T + _ADD], [_T + _ADD], old_shape, old_shape))
        self.assertRejected(self.assess([_T + _ADD], approved=["ALTER TABLE `tabItem` DROP COLUMN `note`"]))

    def test_ran_nothing_recorded_but_schema_changed_is_a_side_effect(self) -> None:
        self.assertRejected(self.assess([]))


class TestNewColumnMatchesPlan(unittest.TestCase):
    def test_matching_type_and_nullability(self) -> None:
        self.assertTrue(new_column_matches_plan("custom_x", [_T + _ADD], _after()))

    def test_different_type_or_missing_column_or_unknown_input(self) -> None:
        self.assertFalse(new_column_matches_plan("custom_x", [_T + _ADD], _after(field_col=_col("text"))))
        self.assertFalse(new_column_matches_plan("custom_x", [_T + _ADD], _after(field_col=_col(nullable="NO"))))
        self.assertFalse(new_column_matches_plan("custom_x", [_T + _ADD], _before()))
        self.assertFalse(new_column_matches_plan("custom_x", None, _after()))
        self.assertFalse(new_column_matches_plan("custom_x", [_T + _ADD], None))

    def test_json_is_reported_as_longtext_and_not_null_is_read_from_the_plan(self) -> None:
        self.assertTrue(new_column_matches_plan(
            "custom_x", [_T + "ADD COLUMN `custom_x` json"], _after(field_col=_col("longtext"))))
        self.assertTrue(new_column_matches_plan(
            "custom_x", [_T + "ADD COLUMN `custom_x` int(11) not null default 0"],
            _after(field_col=_col("int(11)", "NO", "0"))))


class _LiveDb:
    """Live-mode frappe.db double: information_schema answers come from a mutable schema."""

    def __init__(self, *, fail_columns=False, fail_schema=False):
        self.schema = _before()
        self.inserted = set()
        self.fail_columns = fail_columns
        self.fail_schema = fail_schema
        self.ddl_log = []
        self.sql_log = []

    def _cols(self):
        attrs = ("type", "nullable", "default", "key", "charset", "collation", "extra", "comment", "generation")
        return [(n, *(self.schema["columns"][n][a] for a in attrs)) for n in self.schema["order"]]

    def sql(self, query, values=None):
        self.sql_log.append(query)
        q = " ".join(query.upper().split())
        if q.startswith(("ALTER", "CREATE", "DROP")):
            return ()
        if "FROM `TABCUSTOM FIELD`" in q:
            return (("Item-" + values[1], "Data"),) if values[1] in self.inserted else ()
        if "COLUMN_NAME = %S" in q:
            return ((values[1], "varchar(140)"),) if values[1] in self.inserted else ()
        if self.fail_schema and "INFORMATION_SCHEMA.STATISTICS" in q:
            raise RuntimeError("information_schema unavailable")
        if "INFORMATION_SCHEMA.STATISTICS" in q:
            return tuple(self.schema["indexes"])
        if "INFORMATION_SCHEMA.TABLE_CONSTRAINTS" in q:
            return tuple(self.schema["constraints"])
        if "INFORMATION_SCHEMA.CHECK_CONSTRAINTS" in q:
            return tuple(self.schema["checks"])
        if "INFORMATION_SCHEMA.TRIGGERS" in q:
            return ()
        if "INFORMATION_SCHEMA.TABLES" in q:
            return (self.schema["table"],)
        if self.fail_columns and "INFORMATION_SCHEMA.COLUMNS" in q:
            raise RuntimeError("information_schema unavailable")
        if "SELECT COLUMN_NAME, IS_NULLABLE" in q:
            return tuple((r[0], r[2]) for r in self._cols())
        if ", COLUMN_KEY" in q:
            return tuple(self._cols())
        if "COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT" in q:
            return tuple(r[:4] for r in self._cols())
        if "COLUMN_NAME, COLUMN_TYPE, COLUMN_DEFAULT" in q:
            return tuple((r[0], r[1], r[3]) for r in self._cols())
        return ()

    def sql_ddl(self, query):
        self.ddl_log.append(query)
        self.sql(query)  # Frappe's sql_ddl runs the statement through self.sql

    def commit(self):
        pass


class _AdapterHarness:
    def __init__(self, executed_by_field, *, mutate=None, via="sql_ddl", db=None, approved=None):
        self.db = db or _LiveDb()
        self.module = types.SimpleNamespace(db=self.db, clear_cache=lambda **kw: None)
        self.executed_by_field = executed_by_field
        self.mutate = mutate or {}
        self.via = via
        self.approved = approved
        self.adapter = FrappeDeploymentAdapter(frappe_module=self.module, in_memory=False)
        self.module.get_doc = self._get_doc

    def _get_doc(self, args):
        field = args["fieldname"]

        def insert(ignore_permissions=True):
            for stmt in self.executed_by_field[field]:
                getattr(self.module.db, self.via)(stmt)  # goes through the adapter's recorder
            schema = self.db.schema
            schema["columns"][field] = _col()
            schema["order"].append(field)
            if field in self.mutate:
                self.mutate[field](schema)
            self.db.inserted.add(field)

        return types.SimpleNamespace(insert=insert)

    def deploy(self, field="custom_x", dep="dep1"):
        planned = self.approved if self.approved is not None else [_T + f"ADD COLUMN `{field}` varchar(140)"]
        before = self.adapter.take_snapshot("Item", field, dep)
        self.adapter._approved_ddl[dep] = planned
        self.adapter.apply_native_custom_field(dep, "Item", {"fieldname": field, "fieldtype": "Data"})
        after = self.adapter.take_snapshot("Item", field, dep)
        return before, after


class TestAdapterAfterSnapshotIsNotHardCoded(unittest.TestCase):
    def test_approved_statement_only_is_clean(self) -> None:
        h = _AdapterHarness({"custom_x": [_T + _ADD]})
        _, after = h.deploy()
        self.assertFalse(after.unapproved_side_effects)
        self.assertTrue(after.indexes_unchanged)
        self.assertTrue(after.definition_matches)
        self.assertEqual(h.db.ddl_log, [_T + _ADD], "recorded statements are still executed")

    def test_allow_listed_phantom_modify_is_clean(self) -> None:
        h = _AdapterHarness({"custom_x": [_T + _ADD + ", " + _PHANTOM]})
        _, after = h.deploy()
        self.assertFalse(after.unapproved_side_effects)

    def test_unplanned_statement_is_an_unapproved_side_effect(self) -> None:
        h = _AdapterHarness({"custom_x": [_T + _ADD, "ALTER TABLE `tabItem` DROP COLUMN `total`"]})
        self.assertTrue(h.deploy()[1].unapproved_side_effects)

    def test_executed_modify_that_changed_a_column_is_an_unapproved_side_effect(self) -> None:
        def mutate(s):
            s["columns"]["note"] = _col(charset="latin1", collation="latin1_swedish_ci")

        h = _AdapterHarness({"custom_x": [_T + _ADD + ", MODIFY `note` varchar(140) CHARACTER SET latin1"]},
                            mutate={"custom_x": mutate})
        self.assertTrue(h.deploy()[1].unapproved_side_effects)

    def test_ddl_sent_through_db_sql_is_recorded_not_only_sql_ddl(self) -> None:
        """Re-review H1 (4): a hook that alters the table through db.sql is not invisible."""
        h = _AdapterHarness({"custom_x": [_T + _ADD, _T + "ADD CONSTRAINT chk CHECK (`total` > 0)"]}, via="sql")
        _, after = h.deploy()
        self.assertTrue(after.unapproved_side_effects)
        self.assertIn(_T + "ADD CONSTRAINT chk CHECK (`total` > 0)", h.adapter._executed_ddl["dep1"])

    def test_sql_ddl_is_recorded_once_even_though_it_runs_through_db_sql(self) -> None:
        h = _AdapterHarness({"custom_x": [_T + _ADD]})
        h.deploy()
        self.assertEqual(h.adapter._executed_ddl["dep1"], [_T + _ADD])

    def test_recorders_are_removed_after_the_apply(self) -> None:
        h = _AdapterHarness({"custom_x": [_T + _ADD]})
        original = (h.db.sql, h.db.sql_ddl)
        h.deploy()
        self.assertEqual((h.db.sql, h.db.sql_ddl), original)

    def test_definition_matches_is_computed_not_hard_coded(self) -> None:
        def mutate(s):
            s["columns"]["custom_x"] = _col("text")

        h = _AdapterHarness({"custom_x": [_T + _ADD]}, mutate={"custom_x": mutate})
        self.assertFalse(h.deploy()[1].definition_matches)

    def test_missing_approved_plan_fails_closed(self) -> None:
        h = _AdapterHarness({"custom_x": [_T + _ADD]})
        h.adapter.take_snapshot("Item", "custom_x", "dep1")
        h.adapter._applied_deployments.add("dep1")
        self.assertTrue(h.adapter.take_snapshot("Item", "custom_x", "dep1").unapproved_side_effects)

    def test_unreadable_before_schema_fails_closed(self) -> None:
        h = _AdapterHarness({"custom_x": [_T + _ADD]}, db=_LiveDb(fail_schema=True))
        snap = h.adapter.take_snapshot("Item", "custom_x", "dep1")
        self.assertTrue(snap.unapproved_side_effects)
        self.assertEqual(snap.revision_hash, "rev_error")

    def test_applied_state_is_per_deployment_so_the_adapter_can_be_reused(self) -> None:
        """Re-review L: the second deployment on a reused live adapter is not failed closed."""
        h = _AdapterHarness({"custom_x": [_T + _ADD], "custom_y": [_T + "ADD COLUMN `custom_y` varchar(140)"]})
        _, first = h.deploy("custom_x", "dep1")
        before2, second = h.deploy("custom_y", "dep2")
        self.assertFalse(first.unapproved_side_effects)
        self.assertFalse(before2.unapproved_side_effects)
        self.assertIn(("Item", "dep2"), h.adapter._before_schema)
        self.assertFalse(second.unapproved_side_effects, "second deployment must not fail closed")
        self.assertTrue(second.has_col)


class TestLiveCallersNeverFallBackToTheSimulator(unittest.TestCase):
    """Re-review H2 (callers) and M1 (swallowed exceptions)."""

    FIELD = {"fieldname": "custom_live", "fieldtype": "Data", "label": "Live"}

    def _frappe(self, db):
        module = _fake_frappe_modules([], [], db_connected=False)["frappe"]
        module.db = db
        module.session = types.SimpleNamespace(user="Administrator")
        return module

    def test_adapter_is_in_memory_only_when_frappe_is_not_importable(self) -> None:
        with mock.patch.object(endpoints, "frappe", None):
            self.assertTrue(FrappeDeploymentAdapter().in_memory)
        for db in (None, types.SimpleNamespace()):
            with self.subTest(db=db):
                self.assertFalse(FrappeDeploymentAdapter(frappe_module=self._frappe(db)).in_memory)
        self.assertTrue(FrappeDeploymentAdapter(frappe_module=self._frappe(None), in_memory=True).in_memory)

    def test_propose_with_frappe_present_and_db_missing_is_rejected_not_simulated(self) -> None:
        proposal = {"intent": "add_custom_fields", "changes": [dict(self.FIELD)]}
        frappe = self._frappe(None)
        modules = _fake_frappe_modules([], [], db_connected=False)
        with mock.patch.object(endpoints, "frappe", frappe), mock.patch.dict(sys.modules, modules):
            result = endpoints.propose_configuration_change("Item", proposal, user_roles=["System Manager"])
        self.assertEqual(result["status"], "REJECTED")
        self.assertFalse(result["success"])
        self.assertTrue(
            (result.get("ddl_plan") and not result["ddl_plan"]["inspectable"])
            or result.get("disposition") == "REVISION_HASH_UNAVAILABLE",
            result,
        )

    def test_apply_with_frappe_present_and_db_missing_is_rejected_not_simulated(self) -> None:
        frappe = self._frappe(None)
        modules = _fake_frappe_modules([], [], db_connected=False)
        with mock.patch.object(endpoints, "frappe", frappe), mock.patch.dict(sys.modules, modules):
            try:
                result = endpoints.apply_configuration_change(
                    doctype="Item", deployment_id="dep_x", field_def=dict(self.FIELD),
                    user_roles=["System Manager"])
            except Exception as exc:  # a loud failure is also fail-closed
                result = {"status": "ERROR", "success": False, "exc": exc}
        self.assertNotEqual(result.get("status"), "APPLIED", result)
        self.assertFalse(result.get("success"))

    def test_column_read_failure_in_live_mode_returns_none_not_synthetic_columns(self) -> None:
        h = _AdapterHarness({}, db=_LiveDb(fail_columns=True))
        self.assertIsNone(h.adapter.get_table_columns_description("Item"))

    def test_column_read_failure_makes_the_gate_reject_with_a_coded_reason(self) -> None:
        docfields, live = _core_table()
        h = _AdapterHarness({}, db=_LiveDb(fail_columns=True))
        with mock.patch.dict(sys.modules, _fake_frappe_modules(docfields, live)):
            plan = h.adapter.inspect_ddl_plan("Item", dict(self.FIELD))
        self.assertFalse(plan.inspectable)
        self.assertEqual(plan.reason_code, REASON_EXISTING_COLUMNS_MISSING)

    def test_revision_hash_failure_raises_instead_of_a_stand_in(self) -> None:
        h = _AdapterHarness({}, db=_LiveDb(fail_columns=True))
        with self.assertRaises(RevisionHashError):
            h.adapter.get_doctype_revision_hash("Item")

    def test_propose_rejects_when_the_revision_hash_cannot_be_read(self) -> None:
        h = _AdapterHarness({}, db=_LiveDb(fail_columns=True))
        proposal = {"intent": "add_custom_fields", "changes": [dict(self.FIELD)]}
        result = endpoints.propose_configuration_change(
            "Item", proposal, adapter=h.adapter, user_roles=["System Manager"])
        self.assertEqual(result["status"], "REJECTED")
        self.assertEqual(result["disposition"], "REVISION_HASH_UNAVAILABLE")

    def test_apply_rejects_when_the_revision_hash_cannot_be_read(self) -> None:
        h = _AdapterHarness({}, db=_LiveDb(fail_columns=True))
        result = endpoints.apply_configuration_change(
            doctype="Item", deployment_id="dep_x", field_def=dict(self.FIELD), adapter=h.adapter,
            user_roles=["System Manager"])
        self.assertEqual(result["status"], "REJECTED")
        self.assertEqual(result["disposition"], "REVISION_HASH_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
