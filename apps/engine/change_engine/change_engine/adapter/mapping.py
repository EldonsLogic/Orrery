"""Engine mapping and guardrail checks bridging Blueprint steps to change_engine primitives."""
from __future__ import annotations

import re
from typing import Any, Callable

from change_engine.guarded_apply.ddl_plan_gate import (
    APPROVED_DDL_REGEX,
    inspect_frappe_ddl_plan,
)
from change_engine.guarded_apply.safety_guardrails import (
    PROHIBITED_CODE_PROPERTIES,
    PROHIBITED_EXPRESSION_PATTERNS,
    is_locked_doctype,
)
from change_engine.guarded_apply.schema_reconciler import make_bounded_lock_key

ENTITY_TO_DOCTYPE = {
    "customer": "Customer",
    "item": "Item",
    "sales_order": "Sales Order",
    "sales_order_line": "Sales Order Item",
    "delivery_note": "Delivery Note",
    "delivery_note_line": "Delivery Note Item",
    "sales_invoice": "Sales Invoice",
    "sales_invoice_line": "Sales Invoice Item",
    # BPL-032 after BPL-034 (ADR-0055, contract 0.2.0, contracts/examples/engine-mapping-purchasing.json). The engine
    # names are UNVERIFIED until a recorded bench run. A price-list line is a master document (Item Price).
    "supplier": "Supplier",
    "price_list": "Price List",
    "price_list_item": "Item Price",
    "purchase_order": "Purchase Order",
    "purchase_order_line": "Purchase Order Item",
    "purchase_receipt": "Purchase Receipt",
    "purchase_receipt_line": "Purchase Receipt Item",
    "purchase_invoice": "Purchase Invoice",
    "purchase_invoice_line": "Purchase Invoice Item",
    "general_ledger": "GL Entry",
    "tax_ledger": "Tax Rule",
    "audit_log": "Activity Log",
    "user_account": "User",
    "session_token": "Session",
}

# BPL-031 review: where the mapping contract (contracts/examples/engine-mapping-*.json) stores a Blueprint field under a
# name other than its own, {(entity, field): engineField}; None when the contract names no field on the entity's own type
# (the data is stored on another record, such as Item.selling_price on Item Price). A Blueprint hiddenFields mask must land
# on the engine field that holds the data, not on the custom twin entity.add adds next to it (Q-604). A test pins this
# table to the contract files; the engine names are UNVERIFIED until a recorded bench run.
CONTRACT_NATIVE_FIELDS: dict[tuple[str, str], str | None] = {
    ("item", "unit"): "stock_uom",
    ("item", "cost_price"): "valuation_rate",
    ("item", "selling_price"): None,
    ("sales_order", "order_date"): "transaction_date",
    ("sales_order", "warehouse"): "set_warehouse",
    ("sales_order", "discount_percent"): "additional_discount_percentage",
    ("sales_order", "subtotal"): "total",
    ("sales_order", "vat_amount"): "total_taxes_and_charges",
    ("sales_order", "total_amount"): "grand_total",
    ("sales_order_line", "item"): "item_code",
    ("sales_order_line", "quantity"): "qty",
    ("sales_order_line", "unit_price"): "rate",
    ("sales_order_line", "discount_percent"): "discount_percentage",
    ("sales_order_line", "line_total"): "amount",
    ("delivery_note", "sales_order"): None,
    ("delivery_note", "delivery_date"): "posting_date",
    ("delivery_note", "warehouse"): "set_warehouse",
    ("delivery_note_line", "item"): "item_code",
    ("delivery_note_line", "quantity"): "qty",
    ("sales_invoice", "sales_order"): None,
    ("sales_invoice", "invoice_date"): "posting_date",
    ("sales_invoice", "discount_percent"): "additional_discount_percentage",
    ("sales_invoice", "subtotal"): "total",
    ("sales_invoice", "vat_amount"): "total_taxes_and_charges",
    ("sales_invoice", "total_amount"): "grand_total",
    ("sales_invoice_line", "item"): "item_code",
    ("sales_invoice_line", "quantity"): "qty",
    ("sales_invoice_line", "unit_price"): "rate",
    ("sales_invoice_line", "discount_percent"): "discount_percentage",
    ("sales_invoice_line", "line_total"): "amount",
    ("supplier", "supplier_type"): "supplier_group",
    ("supplier", "vat_number"): "tax_id",
    ("price_list_item", "item"): "item_code",
    ("price_list_item", "rate"): "price_list_rate",
    ("purchase_order", "order_date"): "transaction_date",
    ("purchase_order", "expected_date"): "schedule_date",
    ("purchase_order", "warehouse"): "set_warehouse",
    ("purchase_order", "discount_percent"): "additional_discount_percentage",
    ("purchase_order", "subtotal"): "total",
    ("purchase_order", "vat_amount"): "total_taxes_and_charges",
    ("purchase_order", "total_amount"): "grand_total",
    ("purchase_order_line", "item"): "item_code",
    ("purchase_order_line", "quantity"): "qty",
    ("purchase_order_line", "unit_cost"): "price_list_rate",
    ("purchase_order_line", "discount_percent"): "discount_percentage",
    ("purchase_order_line", "line_total"): "amount",
    ("purchase_receipt", "purchase_order"): None,
    ("purchase_receipt", "receipt_date"): "posting_date",
    ("purchase_receipt", "warehouse"): "set_warehouse",
    ("purchase_receipt", "supplier_delivery_ref"): "supplier_delivery_note",
    ("purchase_receipt_line", "item"): "item_code",
    ("purchase_receipt_line", "quantity"): "qty",
    ("purchase_receipt_line", "rejected_quantity"): "rejected_qty",
    ("purchase_invoice", "purchase_order"): None,
    ("purchase_invoice", "supplier_invoice_number"): "bill_no",
    ("purchase_invoice", "invoice_date"): "bill_date",
    ("purchase_invoice", "discount_percent"): "additional_discount_percentage",
    ("purchase_invoice", "subtotal"): "total",
    ("purchase_invoice", "vat_amount"): "total_taxes_and_charges",
    ("purchase_invoice", "total_amount"): "grand_total",
    ("purchase_invoice_line", "item"): "item_code",
    ("purchase_invoice_line", "quantity"): "qty",
    ("purchase_invoice_line", "unit_cost"): "price_list_rate",
    ("purchase_invoice_line", "discount_percent"): "discount_percentage",
    ("purchase_invoice_line", "line_total"): "amount",
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
    r"^ALTER TABLE `tab[A-Za-z0-9_ ]+` ADD COLUMN `custom_[a-z0-9_]+` decimal\(\d+,\d+\)(?: not null default [0-9.]+)?\Z"
)


# SEC-022 / ADR-0051: every role and workflow state the adapter writes carries this reserved prefix. The '-' is
# outside the Blueprint id grammar, so no raw Blueprint id and no built-in engine name can equal a managed name.
ENGINE_NAME_PREFIX = "bp-"
_BLUEPRINT_ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")


class EngineNameError(ValueError):
    """A value that is not a Blueprint id was offered as one; callers refuse the step (fail closed)."""


def _managed_name(blueprint_id: Any) -> str:
    if not isinstance(blueprint_id, str) or not _BLUEPRINT_ID_RE.fullmatch(blueprint_id):
        raise EngineNameError("not a Blueprint id")
    return ENGINE_NAME_PREFIX + blueprint_id


def engine_role_name(role_id: Any) -> str:
    """Adapter-owned engine role name for a Blueprint role id (ADR-0039 item 1, ADR-0051)."""
    return _managed_name(role_id)


def engine_state_name(state_id: Any) -> str:
    """Adapter-owned engine workflow-state name for a Blueprint state id (ADR-0051)."""
    return _managed_name(state_id)


# BPL-032 / ADR-0039 section 2 as narrowed by ADR-0051: the flags of an engine permission rule. The adapter sets
# each one explicitly; report, print, share, import, email and set_user_permissions are always 0.
RULE_FLAGS = ("read", "write", "create", "delete", "submit", "cancel", "amend", "report", "export", "import", "share",
              "print", "email", "set_user_permissions")


def rule_flags(actions: Any, *, masked: bool, submittable: bool) -> dict[str, int]:
    """Level-0 rule flags for one Blueprint grant; empty when the grant gives nothing (fail closed, never widened).

    read needs to be granted, else nothing is. create and write are withheld when the grant masks fields (RM-018,
    until the bench denied cases pass). The engine's own dependencies are honoured by dropping, never adding:
    submit needs a submittable type and write, cancel needs submit, amend needs create and cancel."""
    acts = {a for a in actions if isinstance(a, str)} if isinstance(actions, list) else set()
    if "read" not in acts:
        return {}
    on = {"read"} | (acts & {"delete", "export"})
    if not masked:
        on |= acts & {"create"}
        if "update" in acts:
            on.add("write")
    if submittable and "write" in on and "submit" in acts:
        on.add("submit")
        if "cancel" in acts:
            on.add("cancel")
            if "create" in on:
                on.add("amend")
    return {flag: int(flag in on) for flag in RULE_FLAGS}


def entity_to_doctype(entity_id: str) -> str:
    if entity_id in ENTITY_TO_DOCTYPE:
        return ENTITY_TO_DOCTYPE[entity_id]
    return " ".join(part.capitalize() for part in str(entity_id).replace("-", "_").split("_") if part) or "Custom Entity"


def is_contract_mapped_entity(entity_id: Any) -> bool:
    """True when the mapping contract maps this entity to a built-in engine document type (BPL-031)."""
    return isinstance(entity_id, str) and entity_id in ENTITY_TO_DOCTYPE


# The Blueprint contract's id grammar (contracts/blueprint.schema.json `$defs/id`). Checked at plan time
# (`unsupported_value_type`, and `protected_subject` for protected entities) on `/entities/<id>` pointers,
# `entity.add` subject ids and inline `definition.fields[]` / `definition.relations[]` targets,
# `field.*` / `relation.*` element steps (exact `/entities/<id>/fields/<fid>` or `/entities/<id>/relations/<rid>`
# pointer, single parent matching `<id>`, `subject.id` matching the last pointer segment, and on `field.add` /
# `relation.add`, `definition.id` matching both, else `definition_conflict`), `field.reorder` (exact
# `/entities/<id>/fields` pointer with `bpdiff`'s entity subject `kind="entity"`, `id=<id>`, `parents=[]`,
# validating entity/parent grammar and protection first, else `definition_conflict`),
# link `field.add` and `relation.*` `definition.target`, `field.set_property` / `relation.set_property` `/target`
# (config-only; backend does not map `/target`), `workflow.upsert` / `report.upsert` `definition.entity`, and
# `role.upsert` grant targets. `/options` on `relation.set_property` is always refused at plan time; `/options`
# on `field.set_property` is refused unless the field exists in site config with a known non-link Blueprint type
# and has no `/type` change recorded in the current artifact or any earlier applied artifact (`protected_subject`
# when the offered value names a protected/locked target, else `unsupported_value_type`; because `frappe_backend`
# ignores `/type`, any recorded `/type` change permanently disqualifies the field from the non-link proof).
ENTITY_ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")


def is_valid_entity_id(entity_id: Any) -> bool:
    return isinstance(entity_id, str) and ENTITY_ID_RE.fullmatch(entity_id) is not None


def _protected_key(name: Any) -> str:
    """Comparison key: stripped, runs of whitespace and underscores collapsed to one `_`, case folded (defence in
    depth; the engine folds case and pads trailing spaces in names, so `Gl Entry ` is `GL Entry`)."""
    return re.sub(r"[\s_]+", "_", str(name).strip()).casefold()


# The adapter's own tables (`Change Engine Audit`, `... Blueprint State`, `... Entity Field`, ...) share this name prefix.
# A Blueprint entity whose id or derived type name starts with it would take one of them over, so none may be named so.
_INTERNAL_NAME_PREFIX = "change_engine_"


def is_protected_entity(entity_id: str) -> bool:
    """Compared on a normalised key: `gl_entry`, `GL Entry` and `gl_entry ` are one protected entity. The adapter's own
    internal table names are reserved the same way (BPL-031 review)."""
    if _protected_key(entity_id) in {_protected_key(i) for i in PROTECTED_ENTITY_IDS}:
        return True
    doctype = entity_to_doctype(entity_id)
    if _protected_key(entity_id).startswith(_INTERNAL_NAME_PREFIX) or _protected_key(doctype).startswith(_INTERNAL_NAME_PREFIX):
        return True
    return is_locked_doctype(doctype)


# SEC-022 / ADR-0051 item 3: the document types a Blueprint role may get permission rules on are an allowlist:
# the reviewed mapping above (minus protected entities), plus document types the adapter created itself for an
# unmapped Blueprint entity (custom=1 in this module, see _ensure_doctype_exists). Everything else is refused.
ADAPTER_DOCTYPE_MODULE = "Custom"


def reviewed_grant_doctype(entity_id: Any) -> str | None:
    """Engine document type of a reviewed, unprotected mapped entity; None for any other entity."""
    if not isinstance(entity_id, str) or entity_id not in ENTITY_TO_DOCTYPE or is_protected_entity(entity_id):
        return None
    return ENTITY_TO_DOCTYPE[entity_id]


def grant_plan_reason(
    definition: Any,
    blueprint_entities: set[str],
    own_allowed: Callable[[str], bool] | None = None,
) -> str | None:
    """Plan-time allowlist check of a role.upsert definition's grant targets (ADR-0051 item 3).

    An entity is allowed when it is in the reviewed mapping, or when it is an unmapped entity of this Blueprint
    whose derived document type is adapter-created or not yet on the engine. The apply stage checks again on the
    engine (FrappeRuntimeBackend)."""
    perms = definition.get("permissions") if isinstance(definition, dict) else None
    if perms is not None and not isinstance(perms, list):
        return "unsupported_value_type"
    for p in perms or []:
        entity = p.get("entity") if isinstance(p, dict) else None
        if not is_valid_entity_id(entity):
            return "unsupported_value_type"
        reviewed = reviewed_grant_doctype(entity) is not None
        own = (
            entity not in ENTITY_TO_DOCTYPE
            and entity in blueprint_entities
            and not is_protected_entity(entity)
            and (own_allowed is None or own_allowed(entity))
        )
        if not (reviewed or own):
            return "protected_subject"
    return None


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
    inspection = inspect_frappe_ddl_plan(
        doctype=doctype,
        field_def=frappe_field_def,
        existing_columns_desc=None,
        # Planning-time classification against synthetic standard columns (no live table):
        # explicit offline mode. The live apply gate runs separately and fails closed.
        offline_simulator=True,
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
