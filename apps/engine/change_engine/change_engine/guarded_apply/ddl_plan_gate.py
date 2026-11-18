"""
Change engine DDL Plan Inspection Gate
Implements ADR-001 (Rev 2.3) Sections 6.1 and 6.2:
- Version-pinned Frappe schema diff inspection and approval gating before DDL execution.
- Simulates how Frappe's MariaDBTable and DbColumn.build_for_alter_table calculate
  column and index diffs.
- Supports full Frappe MariaDBTable inspection when frappe is initialized, and
  deterministic pure-Python simulator when running standalone or in unit test.
- Strictly approves plans ONLY IF:
    * Exactly 1 SQL statement
    * Matches: ^ALTER TABLE `tab[A-Za-z0-9_ ]+` ADD COLUMN `custom_[a-z0-9_]+` [A-Za-z0-9_() ]+$
- Rejects plans with unapproved MODIFY COLUMN, DROP INDEX, ADD INDEX, ADD UNIQUE,
  or multiple statements, setting is_approved_additive_only=False and explicit rejection_reason.
"""

import logging
import re
from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DDLPlanInspection:
    inspectable: bool
    statements: List[str]
    is_approved_additive_only: bool
    rejection_reason: Optional[str] = None
    reason_code: Optional[str] = None


# Coded fail-closed reasons (ERP-027). The gate must REJECT, never approve blind.
REASON_FRAPPE_UNAVAILABLE = "DDL_GATE_FRAPPE_UNAVAILABLE"
REASON_FRAPPE_IMPORT_FAILED = "DDL_GATE_FRAPPE_IMPORT_FAILED"
REASON_INSPECTION_FAILED = "DDL_GATE_INSPECTION_FAILED"
REASON_EXISTING_COLUMNS_MISSING = "DDL_GATE_EXISTING_COLUMNS_MISSING"
REASON_TABLE_NOT_FOUND = "DDL_GATE_TABLE_NOT_FOUND"


class FrappeInspectionError(Exception):
    """The Frappe-native inspection could not be completed; the plan must be rejected."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


# ADR-001 Rev 2.3 §6.1/§6.2 Approval Regex (comma permitted strictly inside decimal(w,p))
APPROVED_DDL_REGEX = re.compile(
    r"^ALTER TABLE `tab[A-Za-z0-9_ ]+` ADD COLUMN `custom_[a-z0-9_]+` (?:decimal\(\d+,\d+\)|[A-Za-z0-9_() '.])+$"
)

# MariaDB v15 Type Mapping matching Frappe v15 mariadb/database.py
MARIADB_TYPE_MAP = {
    "Currency": ("decimal", "21,9"),
    "Int": ("int", "11"),
    "Long Int": ("bigint", "20"),
    "Float": ("decimal", "21,9"),
    "Percent": ("decimal", "21,9"),
    "Check": ("int", "1"),
    "Small Text": ("text", ""),
    "Long Text": ("longtext", ""),
    "Code": ("longtext", ""),
    "Text Editor": ("longtext", ""),
    "Markdown Editor": ("longtext", ""),
    "HTML Editor": ("longtext", ""),
    "Date": ("date", ""),
    "Datetime": ("datetime", "6"),
    "Time": ("time", "6"),
    "Text": ("text", ""),
    "Data": ("varchar", "140"),
    "Link": ("varchar", "140"),
    "Dynamic Link": ("varchar", "140"),
    "Password": ("text", ""),
    "Select": ("varchar", "140"),
    "Rating": ("decimal", "3,2"),
    "Read Only": ("varchar", "140"),
    "Attach": ("text", ""),
    "Attach Image": ("text", ""),
    "Signature": ("longtext", ""),
    "Barcode": ("longtext", ""),
    "Geolocation": ("longtext", ""),
    "Duration": ("decimal", "21,9"),
    "Icon": ("varchar", "140"),
    "Phone": ("varchar", "140"),
    "Autocomplete": ("varchar", "140"),
    "JSON": ("json", ""),
}

STANDARD_COLUMNS = ["name", "creation", "modified", "modified_by", "owner", "docstatus", "idx"]


class ColumnDesc(dict):
    """
    Representation of a column description compatible with
    frappe.db.get_table_columns_description().
    Supports both dict lookup ('type') and attribute access (.type).
    """

    def __init__(
        self,
        name: str,
        type: str,
        default: Any = None,
        index: int = 0,
        unique: int = 0,
        nullable: Optional[bool] = None,
    ):
        # ``nullable`` is None when the caller could not read IS_NULLABLE; the gate then never
        # normalises that column (fail closed). Frappe v15 ignores the extra key.
        super().__init__(
            name=name,
            type=type,
            default=default,
            index=int(bool(index)),
            unique=int(bool(unique)),
            nullable=nullable,
        )

    def __getattr__(self, item):
        try:
            return self[item]
        except KeyError:
            raise AttributeError(f"'ColumnDesc' object has no attribute '{item}'")

    def __setattr__(self, item, value):
        self[item] = value


# Only fieldtypes whose Frappe v15 ``DbColumn.get_definition`` emits ``not null default 0``
# qualify (frappe/database/schema.py:201, v15.126.0: ``elif self.fieldtype in ("Currency",
# "Float", "Percent")``). Rating and Duration get NO default clause (NULL default), so a live
# ``0.00`` default on them is real drift and must stay a MODIFY (ERP-027 review H1).
_DECIMAL_FIELDTYPES = ("Currency", "Float", "Percent")


def _canonical_column_type(raw_type: Any) -> str:
    """Canonical form of a column type string: lower case and no whitespace outside quotes.

    Only case and whitespace are treated as equivalent. Any other precision/scale, a different
    type, ``unsigned`` or a synonym stays different (drift). Quoted literals are left as is.
    """
    parts = re.split(r"('(?:[^'\\]|\\.)*')", str(raw_type or ""))
    out = []
    for i, part in enumerate(parts):
        out.append(part if i % 2 else re.sub(r"\s+", "", part.lower()))
    return "".join(out)


class SimulatedDbColumn:
    """Simulates Frappe's DbColumn alter-table calculation."""

    def __init__(
        self,
        table: Any,
        fieldname: str,
        fieldtype: str,
        length: Any = None,
        default: Any = None,
        set_index: int = 0,
        unique: int = 0,
        precision: Any = None,
        options: Any = None,
    ):
        self.table = table
        self.fieldname = fieldname
        self.fieldtype = fieldtype
        self.length = length
        self.default = default
        self.set_index = int(bool(set_index))
        self.unique = int(bool(unique))
        self.precision = precision
        self.options = options

    def get_column_type(self) -> Optional[str]:
        d = MARIADB_TYPE_MAP.get(self.fieldtype)
        if not d:
            return None

        if self.fieldtype == "Int" and self.length and int(self.length) > 11:
            d = MARIADB_TYPE_MAP.get("Long Int")

        coltype = d[0]
        size = d[1] if d[1] else None

        if size:
            if self.fieldtype in ("Currency", "Float", "Percent"):
                width = self.length if self.length else 21
                precision_is_set = self.precision not in (None, "")
                prec = self.precision if precision_is_set else 9
                if int(prec) > int(width):
                    prec = width
                size = f"{int(width)},{int(prec)}"
            elif self.length:
                if coltype == "varchar":
                    int_len = int(self.length)
                    if int_len < 64:
                        int_len = 64
                    size = int_len
                elif coltype == "int" and int(self.length) < 11:
                    size = self.length

        if size is not None:
            coltype = f"{coltype}({size})"

        return coltype

    def get_definition(self, for_modification: bool = False) -> str:
        column_def = self.get_column_type()
        if not column_def:
            return ""

        if self.fieldtype in ("Check", "Int"):
            default_val = int(self.default) if (self.default is not None and str(self.default).isdigit()) else 0
            column_def += f" not null default {default_val}"
        elif self.fieldtype in ("Currency", "Float", "Percent"):
            default_val = float(self.default) if self.default is not None else 0.0
            column_def += f" not null default {default_val if default_val != 0 else 0}"
        elif self.default and str(self.default) not in ("None", "NULL"):
            escaped = str(self.default).replace("'", "\\'")
            column_def += f" default '{escaped}'"
        elif self.default == "NULL":
            column_def += " default NULL"

        if self.unique and not for_modification and (column_def not in ("text", "longtext")):
            column_def += " unique"

        return column_def

    def default_changed(self, current_def: Any) -> bool:
        cur_default = (
            current_def.get("default")
            if isinstance(current_def, dict)
            else getattr(current_def, "default", None)
        )
        cur_type = (
            current_def.get("type", "")
            if isinstance(current_def, dict)
            else getattr(current_def, "type", "")
        )

        if "decimal" in cur_type:
            if cur_default in ("NULL", None, "") and self.default in (None, ""):
                return False
            try:
                cur_f = float(cur_default) if cur_default not in (None, "", "NULL") else 0.0
                new_f = float(self.default) if self.default not in (None, "") else 0.0
                return cur_f != new_f
            except (ValueError, TypeError):
                return True

        if cur_default == "NULL" or cur_default is None:
            cur_default = None
        else:
            cur_default = str(cur_default).lstrip("'").rstrip("'")

        new_default = self.default
        if self.fieldtype in ("Int", "Check"):
            cur_default = int(cur_default) if cur_default is not None else 0
            new_default = int(new_default) if new_default is not None else 0
        elif self.fieldtype in ("Currency", "Float", "Percent"):
            cur_default = float(cur_default) if cur_default is not None else 0.0
            new_default = float(new_default) if new_default is not None else 0.0

        return cur_default != new_default

    def build_for_alter_table(self, current_def: Any) -> None:
        column_type = self.get_column_type()
        if not column_type:
            return

        if not current_def:
            # Column to add
            self.table.add_column.append(self)
            if column_type not in ("text", "longtext"):
                if self.unique:
                    self.table.add_unique.append(self)
                if self.set_index:
                    self.table.add_index.append(self)
            return

        cur_type = current_def.get("type") if isinstance(current_def, dict) else getattr(current_def, "type", "")
        cur_unique = int(bool(current_def.get("unique") if isinstance(current_def, dict) else getattr(current_def, "unique", 0)))
        cur_index = int(bool(current_def.get("index") if isinstance(current_def, dict) else getattr(current_def, "index", 0)))

        # Type change
        if _canonical_column_type(cur_type) != _canonical_column_type(column_type):
            self.table.change_type.append(self)

        # Unique change
        if (self.unique and not cur_unique) and column_type not in ("text", "longtext"):
            self.table.add_unique.append(self)
        elif (cur_unique and not self.unique) and column_type not in ("text", "longtext"):
            self.table.drop_unique.append(self)

        # Default change
        if self.default_changed(current_def):
            self.table.set_default.append(self)

        # Index change
        if (cur_index and not self.set_index) and column_type not in ("text", "longtext"):
            self.table.drop_index.append(self)
        elif (not cur_index and self.set_index) and column_type not in ("text", "longtext"):
            self.table.add_index.append(self)


class SimulatedMariaDBTable:
    """Simulates Frappe's MariaDBTable alter statement formulation."""

    def __init__(self, doctype: str):
        self.doctype = doctype
        self.table_name = f"tab{doctype}"
        self.columns: Dict[str, SimulatedDbColumn] = {}
        self.current_columns: Dict[str, Any] = {}

        self.add_column: List[SimulatedDbColumn] = []
        self.change_type: List[SimulatedDbColumn] = []
        self.change_name: List[SimulatedDbColumn] = []
        self.add_unique: List[SimulatedDbColumn] = []
        self.add_index: List[SimulatedDbColumn] = []
        self.drop_unique: List[SimulatedDbColumn] = []
        self.drop_index: List[SimulatedDbColumn] = []
        self.set_default: List[SimulatedDbColumn] = []

    def alter(self) -> List[str]:
        for col in self.columns.values():
            col.build_for_alter_table(self.current_columns.get(col.fieldname.lower()))

        add_column_query = [
            f"ADD COLUMN `{col.fieldname}` {col.get_definition()}"
            for col in self.add_column
        ]

        columns_to_modify = list(dict.fromkeys(self.change_type + self.set_default))
        modify_column_query = [
            f"MODIFY `{col.fieldname}` {col.get_definition(for_modification=True)}"
            for col in columns_to_modify
        ]
        modify_column_query.extend([
            f"ADD UNIQUE INDEX IF NOT EXISTS {col.fieldname} (`{col.fieldname}`)"
            for col in self.add_unique
        ])

        add_index_query = [
            f"ADD INDEX `{col.fieldname}_index`(`{col.fieldname}`)"
            for col in self.add_index
        ]

        drop_index_query = []
        for col in list(dict.fromkeys(self.drop_index + self.drop_unique)):
            if col.fieldname == "name":
                continue
            cur_col = self.current_columns.get(col.fieldname.lower())
            if cur_col:
                cur_unique = cur_col.get("unique") if isinstance(cur_col, dict) else getattr(cur_col, "unique", 0)
                cur_index = cur_col.get("index") if isinstance(cur_col, dict) else getattr(cur_col, "index", 0)
                if cur_unique and not col.unique:
                    drop_index_query.append(f"DROP INDEX `{col.fieldname}`")
                if cur_index and not col.set_index:
                    drop_index_query.append(f"DROP INDEX `{col.fieldname}_index`")

        statements = []
        for query_parts in [add_column_query, drop_index_query, modify_column_query, add_index_query]:
            if query_parts:
                query_body = ", ".join(query_parts)
                statements.append(f"ALTER TABLE `{self.table_name}` {query_body}")

        return statements


def validate_ddl_plan(statements: List[str]) -> Tuple[bool, Optional[str]]:
    """
    Strictly enforces ADR-001 Rev 2.3 §6.1/§6.2:
    - Exactly 1 SQL statement.
    - Matches: ^ALTER TABLE `tab[A-Za-z0-9_ ]+` ADD COLUMN `custom_[a-z0-9_]+` [A-Za-z0-9_() ]+$
    - Zero MODIFY COLUMN, DROP INDEX, ADD INDEX, ADD UNIQUE statements.
    """
    if not statements:
        return False, "No DDL statements produced for single field deployment (field may already exist or no-op)."

    if len(statements) > 1:
        # Provide specific diagnostics if unapproved operations were found across statements
        for stmt in statements:
            if "MODIFY" in stmt:
                return False, f"Unapproved MODIFY COLUMN detected in updatedb() diff: {statements}"
            if "DROP INDEX" in stmt:
                return False, f"Unapproved DROP INDEX detected in updatedb() diff: {statements}"
            if "ADD INDEX" in stmt:
                return False, f"Unapproved ADD INDEX detected in updatedb() diff: {statements}"
            if "ADD UNIQUE" in stmt:
                return False, f"Unapproved ADD UNIQUE detected in updatedb() diff: {statements}"
        return False, f"Expected exactly 1 DDL statement, but produced {len(statements)}: {statements}"

    stmt = statements[0]

    # Explicit check for unapproved operation keywords
    if "MODIFY" in stmt:
        return False, f"Unapproved MODIFY COLUMN detected in updatedb() diff: '{stmt}'"
    if "DROP INDEX" in stmt:
        return False, f"Unapproved DROP INDEX detected in updatedb() diff: '{stmt}'"
    if "ADD INDEX" in stmt:
        return False, f"Unapproved ADD INDEX detected in updatedb() diff: '{stmt}'"
    if "ADD UNIQUE" in stmt:
        return False, f"Unapproved ADD UNIQUE detected in updatedb() diff: '{stmt}'"

    # Strictly check approved single ADD COLUMN regex pattern
    if not APPROVED_DDL_REGEX.match(stmt):
        return False, f"DDL statement does not match approved additive ADD COLUMN pattern: '{stmt}'"

    return True, None


def _split_alter_clauses(statement: str) -> Tuple[str, List[str]]:
    """Split ``ALTER TABLE `t` a, b, c`` into (``ALTER TABLE `t```, [clauses]) ignoring commas
    inside parentheses (``decimal(21,9)``). Returns ("", []) when it is not an ALTER TABLE."""
    m = re.match(r"^\s*ALTER TABLE\s+(`[^`]+`)\s+(.*)$", statement.strip(), re.S | re.I)
    if not m:
        return "", []
    clauses, depth, cur = [], 0, []
    for ch in m.group(2):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            clauses.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    clauses.append("".join(cur).strip())
    return m.group(1), [c for c in clauses if c]


def _norm_sql(text: str) -> str:
    return re.sub(r"\s+", " ", str(text)).strip().lower()


def assess_applied_ddl(
    doctype: str,
    fieldname: str,
    approved_statements: Optional[List[str]],
    executed_statements: Optional[List[str]],
    before_schema: Optional[Dict[str, Any]],
    after_schema: Optional[Dict[str, Any]],
) -> Tuple[bool, Optional[str]]:
    """Compare what actually ran with the approved plan (ERP-027 review H1/M1).

    Returns ``(unapproved_side_effects, reason)``. Fail closed: unknown input is a side effect.

    * Every executed statement must be an ``ALTER TABLE`` on the target table.
    * The executed ``ADD COLUMN`` clauses must equal the approved ones.
    * Frappe's own apply re-emits "phantom" ``MODIFY`` clauses that the gate normalised away
      (651 raw clauses on the live bench). They are tolerated ONLY when they are ``MODIFY``
      and the before/after table schemas (type, nullability, default, key, indexes) prove every
      pre-existing column and index is unchanged and exactly ``fieldname`` was added.
    * Anything else (other clause kinds, other tables, other DDL) is an unapproved side effect.

    ``*_schema`` are ``{"columns": {name: (type, nullable, default, key)}, "indexes": set(...)}``.
    """
    if approved_statements is None or executed_statements is None:
        return True, "approved plan or executed statements are unknown"
    if before_schema is None or after_schema is None:
        return True, "before/after table schema is unknown"

    if not executed_statements and before_schema == after_schema:
        return False, None  # nothing ran and nothing changed (clean failure)

    table = f"`tab{doctype}`".lower()
    approved_adds: List[str] = []
    for stmt in approved_statements:
        t, clauses = _split_alter_clauses(stmt)
        if t.lower() != table:
            return True, f"approved plan statement does not target {table}"
        approved_adds.extend(_norm_sql(c) for c in clauses if c.upper().startswith("ADD COLUMN"))

    executed_adds: List[str] = []
    extra_modify = False
    for stmt in executed_statements:
        t, clauses = _split_alter_clauses(stmt)
        if not clauses or t.lower() != table:
            return True, f"executed DDL is not an ALTER TABLE on {table}: {stmt[:120]}"
        for c in clauses:
            up = c.upper()
            if up.startswith("ADD COLUMN"):
                executed_adds.append(_norm_sql(c))
            elif up.startswith("MODIFY"):
                extra_modify = True
            else:
                return True, f"executed DDL contains an unapproved clause: {c[:120]}"
    if sorted(executed_adds) != sorted(approved_adds):
        return True, "executed ADD COLUMN clauses differ from the approved plan"

    before_cols, after_cols = before_schema.get("columns", {}), after_schema.get("columns", {})
    if set(after_cols) - set(before_cols) != {fieldname}:
        return True, "table columns after apply are not exactly the previous set plus the new field"
    for name, definition in before_cols.items():
        if after_cols.get(name) != definition:
            return True, f"existing column '{name}' changed during apply"
    if before_schema.get("indexes") != after_schema.get("indexes"):
        return True, "table indexes changed during apply"
    if extra_modify:
        logger.warning(
            "DDL apply on %s re-emitted MODIFY clauses beyond the approved plan; "
            "before/after schema proves them no-ops", doctype,
        )
    return False, None


def _col_get(col: Any, key: str, default: Any = None) -> Any:
    return col.get(key, default) if isinstance(col, dict) else getattr(col, key, default)


def _col_with(col: Any, **overrides: Any) -> Any:
    """Copy a live column description and override only the given keys (extra keys kept)."""
    if isinstance(col, dict):
        copy = ColumnDesc(name=col.get("name", ""), type=col.get("type", ""))
        copy.update(col)
        copy.update(overrides)
        return copy
    copy = ColumnDesc(name=getattr(col, "name", ""), type=getattr(col, "type", ""))
    for key in ("default", "index", "unique", "nullable"):
        if hasattr(col, key):
            copy[key] = getattr(col, key)
    copy.update(overrides)
    return copy


def _canonicalize_current_column_types(current_columns: Dict[str, Any]) -> None:
    """Rewrite equivalent spellings of the live column type (case, whitespace outside quotes)
    to the canonical form Frappe generates, so Frappe's strict string comparison does not
    report them as a type change. Real precision/scale/type differences are left untouched.
    """
    for cname, cur_col in list(current_columns.items()):
        raw_type = _col_get(cur_col, "type", "")
        canon = _canonical_column_type(raw_type)
        if not raw_type or canon == raw_type:
            continue
        current_columns[cname] = _col_with(cur_col, type=canon)


def _normalize_zero_decimal_defaults(
    table_columns: Dict[str, Any],
    current_columns: Dict[str, Any],
    *,
    exclude_fieldname: str,
) -> None:
    """Normalize MariaDB INFORMATION_SCHEMA `'0.000000000'` defaults on untouched decimal
    columns when the DocField default is empty/None (matches SimulatedDbColumn semantics
    and avoids Frappe DbColumn.default_changed_for_decimal phantom MODIFY noise).

    Only Currency/Float/Percent qualify (see ``_DECIMAL_FIELDTYPES``) and only when the live
    column is explicitly ``NOT NULL`` (``nullable is False``): Frappe's phantom MODIFY is
    ``not null default 0``, so on a NULLable column it is a real nullability change that
    must not be hidden. Unknown nullability is treated as nullable (fail closed).
    """
    for cname, col in table_columns.items():
        if cname == exclude_fieldname:
            continue
        if getattr(col, "fieldtype", None) not in _DECIMAL_FIELDTYPES:
            continue
        if getattr(col, "default", None) not in (None, ""):
            continue
        cur_col = current_columns.get(cname.lower())
        if not cur_col:
            continue
        if _col_get(cur_col, "nullable") is not False:
            continue
        cur_type = _col_get(cur_col, "type", "")
        if not _canonical_column_type(cur_type).startswith("decimal("):
            continue
        cur_def = _col_get(cur_col, "default")
        if cur_def in (None, "", "NULL"):
            continue
        try:
            if float(str(cur_def).strip("'\"")) == 0.0:
                current_columns[cname.lower()] = _col_with(cur_col, default=None)
        except (ValueError, TypeError):
            continue


def _inspect_with_frappe_mariadb_table(
    doctype: str,
    field_def: Dict[str, Any],
    existing_columns_desc: Optional[List[Any]] = None,
) -> List[str]:
    """Inspect the DDL plan with Frappe's own MariaDBTable on a live bench.

    Fail closed: any problem raises ``FrappeInspectionError`` (a coded reason) and the caller
    rejects the plan. There is no fallback to the simulator on this path (ERP-027 H2).
    """
    try:
        import frappe
    except Exception as exc:
        raise FrappeInspectionError(REASON_FRAPPE_UNAVAILABLE, f"frappe cannot be imported: {exc}")
    try:
        from frappe.database.mariadb.schema import MariaDBTable
        from frappe.database.schema import DbColumn
    except Exception as exc:
        raise FrappeInspectionError(
            REASON_FRAPPE_IMPORT_FAILED, f"Frappe schema classes cannot be imported: {exc}"
        )

    db = getattr(frappe, "db", None)
    if db is None or not hasattr(db, "sql_ddl"):
        raise FrappeInspectionError(
            REASON_FRAPPE_UNAVAILABLE, "frappe.db is not connected; the live DDL plan cannot be inspected"
        )
    if existing_columns_desc is None:
        raise FrappeInspectionError(
            REASON_EXISTING_COLUMNS_MISSING,
            "existing column definitions were not supplied by the caller; refusing to inspect blind",
        )

    try:
        table = MariaDBTable(doctype)
        table.current_columns = {c["name"].lower(): c for c in existing_columns_desc}

        new_fname = field_def["fieldname"]
        _canonicalize_current_column_types(table.current_columns)
        _normalize_zero_decimal_defaults(
            table.columns,
            table.current_columns,
            exclude_fieldname=new_fname,
        )

        new_col = DbColumn(
            table=table,
            fieldname=new_fname,
            fieldtype=field_def.get("fieldtype", "Data"),
            length=field_def.get("length"),
            default=field_def.get("default"),
            set_index=field_def.get("search_index") or field_def.get("index") or 0,
            options=field_def.get("options"),
            unique=field_def.get("unique") or 0,
            precision=field_def.get("precision"),
        )
        table.columns[new_fname] = new_col

        statements: List[str] = []
        original_sql_ddl = db.sql_ddl
        try:
            db.sql_ddl = lambda q: statements.append(q)
            table.alter()
        finally:
            db.sql_ddl = original_sql_ddl
        return statements
    except FrappeInspectionError:
        raise
    except Exception as exc:
        logger.exception("DDL plan gate: Frappe inspection failed for %s", doctype)
        raise FrappeInspectionError(
            REASON_INSPECTION_FAILED, f"Frappe DDL plan inspection raised {type(exc).__name__}: {exc}"
        )


def _simulate_alter_statements(
    doctype: str,
    field_def: Dict[str, Any],
    existing_columns_desc: Optional[List[Any]] = None,
    doctype_fields: Optional[List[Dict[str, Any]]] = None,
    meta: Optional[Any] = None,
) -> List[str]:
    """Pure-Python alter statement simulation matching Frappe v15 MariaDBTable."""
    table = SimulatedMariaDBTable(doctype)

    # 1. Populate current_columns from existing_columns_desc or defaults
    if existing_columns_desc is not None:
        for c in existing_columns_desc:
            col_desc = c if isinstance(c, ColumnDesc) else ColumnDesc(
                name=c.get("name") if isinstance(c, dict) else getattr(c, "name"),
                type=c.get("type") if isinstance(c, dict) else getattr(c, "type"),
                default=c.get("default") if isinstance(c, dict) else getattr(c, "default", None),
                index=c.get("index") if isinstance(c, dict) else getattr(c, "index", 0),
                unique=c.get("unique") if isinstance(c, dict) else getattr(c, "unique", 0),
            )
            table.current_columns[col_desc.name.lower()] = col_desc
    else:
        for col_name in STANDARD_COLUMNS:
            table.current_columns[col_name.lower()] = ColumnDesc(
                name=col_name,
                type="varchar(140)" if col_name not in ("creation", "modified") else "datetime(6)",
            )

    # 2. Populate DocType metadata columns (if provided)
    fields = []
    if doctype_fields is not None:
        fields = doctype_fields
    elif meta is not None:
        fields = getattr(meta, "fields", [])

    for f in fields:
        fname = f.get("fieldname") if isinstance(f, dict) else getattr(f, "fieldname", None)
        if not fname:
            continue
        ftype = f.get("fieldtype") if isinstance(f, dict) else getattr(f, "fieldtype", "Data")
        flen = f.get("length") if isinstance(f, dict) else getattr(f, "length", None)
        fdef = f.get("default") if isinstance(f, dict) else getattr(f, "default", None)
        fidx = f.get("search_index") or f.get("index") if isinstance(f, dict) else getattr(f, "search_index", 0)
        funi = f.get("unique") if isinstance(f, dict) else getattr(f, "unique", 0)
        fprec = f.get("precision") if isinstance(f, dict) else getattr(f, "precision", None)

        col = SimulatedDbColumn(
            table=table,
            fieldname=fname,
            fieldtype=ftype,
            length=flen,
            default=fdef,
            set_index=fidx,
            unique=funi,
            precision=fprec,
        )
        table.columns[fname] = col

    # 3. Add proposed field definition
    new_fname = field_def["fieldname"]
    new_col = SimulatedDbColumn(
        table=table,
        fieldname=new_fname,
        fieldtype=field_def.get("fieldtype", "Data"),
        length=field_def.get("length"),
        default=field_def.get("default"),
        set_index=field_def.get("search_index") or field_def.get("index") or field_def.get("set_index") or 0,
        unique=field_def.get("unique") or 0,
        precision=field_def.get("precision"),
        options=field_def.get("options"),
    )
    table.columns[new_fname] = new_col

    # 4. Generate statements
    return table.alter()


def inspect_frappe_ddl_plan(
    doctype: str,
    field_def: Dict[str, Any],
    existing_columns_desc: Optional[List[Any]] = None,
    doctype_fields: Optional[List[Dict[str, Any]]] = None,
    meta: Optional[Any] = None,
    offline_simulator: bool = False,
) -> DDLPlanInspection:
    """
    Inspects Frappe's updatedb() DDL plan for a proposed field deployment
    and validates approval according to ADR-001 Rev 2.3 (§6.1/§6.2).

    Parameters:
    - doctype: Target DocType name (e.g. 'Sales Order')
    - field_def: Single field definition dict (must include 'fieldname')
    - existing_columns_desc: Optional list of column descriptions from DB
    - doctype_fields: Optional list of existing DocType field definitions
    - meta: Optional DocType meta object
    - offline_simulator: explicit test/offline mode (default False). True uses ONLY the
      pure-Python simulator. False uses ONLY Frappe's own MariaDBTable and fails closed (coded
      rejection) when that inspection cannot run; it never falls back to the simulator.
    """
    if not doctype or not isinstance(doctype, str) or not doctype.strip():
        return DDLPlanInspection(
            inspectable=False,
            statements=[],
            is_approved_additive_only=False,
            rejection_reason="Invalid doctype: must be non-empty string",
        )

    if not field_def or not isinstance(field_def, dict) or not field_def.get("fieldname"):
        return DDLPlanInspection(
            inspectable=False,
            statements=[],
            is_approved_additive_only=False,
            rejection_reason="Invalid field_def: missing 'fieldname'",
        )

    is_single_dt = doctype in ("Change Engine Settings", "System Settings") or bool(getattr(meta, "issingle", 0))
    if not is_single_dt:
        try:
            import frappe
            if hasattr(frappe, "db") and frappe.db is not None and hasattr(frappe, "get_meta"):
                dt_meta = frappe.get_meta(doctype)
                if getattr(dt_meta, "issingle", 0):
                    is_single_dt = True
        except Exception:
            pass

    if is_single_dt:
        return DDLPlanInspection(
            inspectable=False,
            statements=[],
            is_approved_additive_only=False,
            rejection_reason=(
                f"DocType '{doctype}' is a Single DocType (stored in tabSingles) and does not "
                "have a physical database table. Please target a standard transactional DocType "
                "(e.g., Sales Order, Customer, or ToDo)."
            ),
        )

    if offline_simulator:
        try:
            statements = _simulate_alter_statements(
                doctype=doctype,
                field_def=field_def,
                existing_columns_desc=existing_columns_desc,
                doctype_fields=doctype_fields,
                meta=meta,
            )
        except Exception as exc:
            return DDLPlanInspection(
                inspectable=False,
                statements=[],
                is_approved_additive_only=False,
                rejection_reason=f"DDL Plan inspection simulator failed: {exc}",
                reason_code=REASON_INSPECTION_FAILED,
            )
    else:
        try:
            statements = _inspect_with_frappe_mariadb_table(
                doctype=doctype,
                field_def=field_def,
                existing_columns_desc=existing_columns_desc,
            )
        except FrappeInspectionError as exc:
            return DDLPlanInspection(
                inspectable=False,
                statements=[],
                is_approved_additive_only=False,
                rejection_reason=f"[{exc.code}] {exc.message}",
                reason_code=exc.code,
            )

    is_approved, rejection_reason = validate_ddl_plan(statements)
    return DDLPlanInspection(
        inspectable=True,
        statements=statements,
        is_approved_additive_only=is_approved,
        rejection_reason=rejection_reason,
    )
