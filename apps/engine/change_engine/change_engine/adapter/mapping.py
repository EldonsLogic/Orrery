"""Engine mapping and guardrail checks bridging Blueprint steps to change_engine primitives."""
from __future__ import annotations

import re
from typing import Any

from change_engine.guarded_apply.ddl_plan_gate import (
    APPROVED_DDL_REGEX,
    ColumnDesc,
    STANDARD_COLUMNS,
    inspect_frappe_ddl_plan,
)
from change_engine.guarded_apply.safety_guardrails import (
    PROHIBITED_CODE_PROPERTIES,
    PROHIBITED_EXPRESSION_PATTERNS,
    ZONE_2_LOCKED_DOCTYPES,
)
from change_engine.guarded_apply.schema_reconciler import make_bounded_lock_key

ENTITY_TO_DOCTYPE = {
    "customer": "Customer",
    "item": "Item",
    "sales_order": "Sales Order",
    "sales_order_line": "Sales Order Item",
    "sales_invoice": "Sales Invoice",
    "sales_invoice_line": "Sales Invoice Item",
    "general_ledger": "GL Entry",
    "tax_ledger": "Tax Rule",
    "audit_log": "Activity Log",
    "user_account": "User",
    "session_token": "Session",
}

PROTECTED_ENTITY_IDS = {
    "general_ledger",
    "tax_ledger",
    "audit_log",
    "user_account",
    "session_token",
}

BLUEPRINT_TO_FRAPPE_FIELDTYPE = {
    "string": "Data",
    "text": "Small Text",
    "integer": "Int",
    "decimal": "Float",
    "money": "Currency",
    "percent": "Percent",
    "boolean": "Check",
    "date": "Date",
    "datetime": "Datetime",
    "select": "Select",
    "link": "Link",
    "phone": "Phone",
    "email": "Data",
}

SUPPORTED_BLUEPRINT_TYPES = set(BLUEPRINT_TO_FRAPPE_FIELDTYPE)
SEMANTIC_PROPS = {"/type", "/unique", "/indexed", "/precision", "/maxLength", "/required", "/computed"}

_SAFE_IDENT_RE = re.compile(r"^[a-z0-9_]+$")
_DECIMAL_ADD_RE = re.compile(
    r"^ALTER TABLE `tab[A-Za-z0-9_ ]+` ADD COLUMN `custom_[a-z0-9_]+` decimal\(\d+,\d+\)(?: not null default [0-9.]+)?$"
)


def entity_to_doctype(entity_id: str) -> str:
    if entity_id in ENTITY_TO_DOCTYPE:
        return ENTITY_TO_DOCTYPE[entity_id]
    return " ".join(part.capitalize() for part in str(entity_id).replace("-", "_").split("_") if part) or "Custom Entity"


def is_protected_entity(entity_id: str) -> bool:
    if entity_id in PROTECTED_ENTITY_IDS:
        return True
    doctype = entity_to_doctype(entity_id)
    return doctype in ZONE_2_LOCKED_DOCTYPES


def has_prohibited_expression(value: Any) -> bool:
    """Enforce PRD-001 / safety_guardrails no-generated-code invariant recursively."""
    if isinstance(value, str):
        return bool(PROHIBITED_EXPRESSION_PATTERNS.search(value))
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).strip().lower() in PROHIBITED_CODE_PROPERTIES:
                return True
            if has_prohibited_expression(item):
                return True
    elif isinstance(value, list):
        return any(has_prohibited_expression(item) for item in value)
    return False


def _sanitize_custom_fieldname(field_id: str) -> str:
    cleaned = re.sub(r"[^a-z0-9_]", "_", str(field_id).lower()).strip("_")
    if not cleaned:
        cleaned = "field"
    return f"custom_{cleaned}"


def inspect_field_ddl(entity_id: str, field_def: dict[str, Any]) -> tuple[bool, list[str], str | None]:
    """Run change_engine DDL plan gate for a single Blueprint field definition.

    Returns (is_approved_additive, statements, gate_reason_code).
    """
    bp_type = field_def.get("type", "string")
    if bp_type not in SUPPORTED_BLUEPRINT_TYPES:
        return False, [], "unsupported_value_type"

    doctype = entity_to_doctype(entity_id)
    frappe_ftype = BLUEPRINT_TO_FRAPPE_FIELDTYPE[bp_type]
    safe_fname = _sanitize_custom_fieldname(str(field_def.get("id", "field")))
    frappe_field_def = {
        "fieldname": safe_fname,
        "fieldtype": frappe_ftype,
        "unique": 1 if field_def.get("unique") else 0,
        "search_index": 1 if field_def.get("indexed") else 0,
        "precision": field_def.get("precision"),
        "length": field_def.get("maxLength"),
    }
    existing_cols = [
        ColumnDesc(
            name=col,
            type="datetime(6)" if col in ("creation", "modified") else "varchar(140)",
        )
        for col in STANDARD_COLUMNS
    ]
    inspection = inspect_frappe_ddl_plan(
        doctype=doctype,
        field_def=frappe_field_def,
        existing_columns_desc=existing_cols,
    )
    statements = list(inspection.statements)
    if field_def.get("unique") or field_def.get("indexed"):
        return False, statements, "unique_or_index"
    if len(statements) > 1:
        return False, statements, "multi_statement"
    if inspection.is_approved_additive_only:
        return True, statements, None
    if len(statements) == 1 and (APPROVED_DDL_REGEX.match(statements[0]) or _DECIMAL_ADD_RE.match(statements[0])):
        return True, statements, None
    return False, statements, "storage_not_additive"


def plan_statements_for_step(step: dict[str, Any]) -> list[str]:
    """Generate internal engine storage statements (1 statement per step, never destructive)."""
    kind = step["kind"]
    pointer = step["pointer"]
    subject = step["subject"]
    params = step.get("params", {})

    if kind == "entity.add":
        doctype = entity_to_doctype(str(subject.get("id") or "entity"))
        return [f"CREATE TABLE IF NOT EXISTS `tab{doctype}` (name VARCHAR(140) PRIMARY KEY)"]
    if kind == "field.add":
        parents = subject.get("parents") or []
        entity_id = str(parents[0]["id"]) if parents else "entity"
        defn = params.get("definition") or {"id": subject.get("id", "field"), "type": "string"}
        _, stmts, _ = inspect_field_ddl(entity_id, defn)
        if stmts:
            return [stmts[0]]
        doctype = entity_to_doctype(entity_id)
        fname = _sanitize_custom_fieldname(str(subject.get("id") or "field"))
        return [f"ALTER TABLE `tab{doctype}` ADD COLUMN `{fname}` varchar(140)"]
    if kind == "relation.add":
        parents = subject.get("parents") or []
        entity_id = str(parents[0]["id"]) if parents else "entity"
        doctype = entity_to_doctype(entity_id)
        fname = _sanitize_custom_fieldname(str(subject.get("id") or "rel"))
        return [f"ALTER TABLE `tab{doctype}` ADD COLUMN `{fname}` varchar(140)"]
    if kind.endswith((".quarantine", ".disable")):
        state = "quarantined" if kind.endswith(".quarantine") else "disabled"
        return [f"UPDATE `tabChange Engine Element` SET state = '{state}' WHERE pointer = ?"]
    return [f"UPDATE `tabChange Engine Element` SET config = ? WHERE pointer = '{pointer}'"]


def bounded_site_lock_key(tenant_id: str, blueprint_id: str) -> str:
    """Delegate bounded advisory lock key construction (<= 64 chars) to schema_reconciler."""
    return make_bounded_lock_key(tenant_id, blueprint_id)
