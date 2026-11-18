"""Data tables for DSC-013: source model disposition, neutral name -> Blueprint target, record checks
and type compatibility. This file FIXES the neutral vocabulary of connectors/odoo/mapping.py (Q-114).
Extend by adding lines. Targets: `entity.field` (template field id), `entity#relation_id`,
`~entity.field` (value inverted), `@location.labels|id`, `@company.<key>`, `@ref.<bucket>`,
`@routing`, `!reason` (no Blueprint home, reported unmapped with that reason code).
Every `entity.field` must exist in the trading-distribution template (checked at load)."""
from __future__ import annotations

# model | kind | args | human reason raised for the whole model (optional)
_MODELS = """
res.company | company | |
res.currency | reference | |
res.partner | entity | customer supplier | partner_role_split
product.category | reference | |
product.template | entity | item |
product.product | entity | item |
uom.uom | reference | |
account.tax | reference | | tax_semantics
account.account | reference | | ledger_semantics
account.journal | reference | | ledger_semantics
sale.order | entity | sales_order |
sale.order.line | entity | sales_order_line |
purchase.order | entity | purchase_order |
purchase.order.line | entity | purchase_order_line |
account.move | entity | sales_invoice purchase_invoice credit_note | invoice_routing
account.move.line | entity | sales_invoice_line purchase_invoice_line credit_note_line | ledger_semantics
account.payment | entity | payment |
stock.warehouse | location | warehouse |
stock.location | unmapped | no_blueprint_entity |
stock.quant | unmapped | stock_semantics | stock_semantics
"""

# neutral name | targets
_FIELDS = """
record.source_id !bookkeeping
record.label !bookkeeping
record.created_at !bookkeeping
record.updated_at !bookkeeping
record.active ~customer.disabled ~supplier.disabled ~item.disabled
record.company !bookkeeping
record.currency !bookkeeping
company.name @company.legalName
company.currency @company.currency
company.tax_number @company.vatNumber
currency.code @ref.currencies
currency.symbol !no_blueprint_home
currency.rounding !no_blueprint_home
party.name customer.customer_name supplier.supplier_name
party.code customer.customer_code supplier.supplier_code
party.tax_number customer.vat_number supplier.vat_number
party.email customer.email supplier.email
party.phone customer.phone supplier.phone
party.mobile customer.phone supplier.phone
party.address_line1 !no_blueprint_home
party.city customer.city supplier.city
party.country !no_blueprint_home
party.is_organisation customer.customer_type supplier.supplier_type
party.customer_rank @routing
party.supplier_rank @routing
party.parent !no_blueprint_home
party.payment_terms !semantic_mismatch
item_group.name @ref.item_groups
item_group.parent !no_blueprint_home
item.name item.item_name
item.code item.item_code
item.group item.item_group
item.kind !stock_semantics
item.sale_price item.selling_price
item.cost item.cost_price
item.unit item.unit
item.sale_taxes !tax_semantics
item.purchase_taxes !tax_semantics
item.barcode item.barcode
item.template !variant_structure
unit.name @ref.units
unit.category !no_blueprint_home
unit.factor !no_blueprint_home
tax.name @ref.taxes
tax.rate !tax_semantics
tax.computation !tax_semantics
tax.scope !tax_semantics
tax.included_in_price !tax_semantics
ledger_account.code @ref.ledger_accounts
ledger_account.name @ref.ledger_accounts
ledger_account.kind !ledger_semantics
ledger_account.reconcilable !ledger_semantics
journal.name @ref.journals
journal.code @ref.journals
journal.kind !ledger_semantics
journal.default_account !ledger_semantics
sales_order.number !numbering_is_config
sales_order.customer sales_order.customer
sales_order.ordered_at sales_order.order_date
sales_order.status !workflow_state
sales_order.net_total sales_order.subtotal
sales_order.tax_total sales_order.vat_amount
sales_order.gross_total sales_order.total_amount
sales_order.lines sales_order#lines
sales_order.warehouse sales_order.warehouse
sales_order_line.order !implicit_parent_link
sales_order_line.item sales_order_line.item
sales_order_line.description sales_order_line.description
sales_order_line.quantity sales_order_line.quantity
sales_order_line.unit !no_blueprint_home
sales_order_line.unit_price sales_order_line.unit_price
sales_order_line.discount_percent sales_order_line.discount_percent
sales_order_line.taxes !tax_semantics
sales_order_line.net_amount sales_order_line.line_total
purchase_order.number !numbering_is_config
purchase_order.supplier purchase_order.supplier
purchase_order.ordered_at purchase_order.order_date
purchase_order.status !workflow_state
purchase_order.net_total purchase_order.subtotal
purchase_order.tax_total purchase_order.vat_amount
purchase_order.gross_total purchase_order.total_amount
purchase_order.lines purchase_order#lines
purchase_order_line.order !implicit_parent_link
purchase_order_line.item purchase_order_line.item
purchase_order_line.description purchase_order_line.description
purchase_order_line.quantity purchase_order_line.quantity
purchase_order_line.unit_price purchase_order_line.unit_cost
purchase_order_line.taxes !tax_semantics
purchase_order_line.net_amount purchase_order_line.line_total
invoice.number !numbering_is_config
invoice.kind @routing
invoice.party sales_invoice.customer credit_note.customer purchase_invoice.supplier
invoice.issued_on sales_invoice.invoice_date purchase_invoice.invoice_date credit_note.credit_date
invoice.due_on sales_invoice.due_date purchase_invoice.due_date
invoice.status !workflow_state
invoice.payment_status !semantic_mismatch
invoice.net_total sales_invoice.subtotal purchase_invoice.subtotal credit_note.subtotal
invoice.tax_total sales_invoice.vat_amount purchase_invoice.vat_amount credit_note.vat_amount
invoice.gross_total sales_invoice.total_amount purchase_invoice.total_amount credit_note.total_amount
invoice.journal !ledger_semantics
invoice.lines sales_invoice#lines purchase_invoice#lines credit_note#lines
invoice_line.invoice !implicit_parent_link
invoice_line.ledger_account !ledger_semantics
invoice_line.item sales_invoice_line.item purchase_invoice_line.item credit_note_line.item
invoice_line.description sales_invoice_line.description purchase_invoice_line.description credit_note_line.description
invoice_line.quantity sales_invoice_line.quantity purchase_invoice_line.quantity credit_note_line.quantity
invoice_line.unit_price sales_invoice_line.unit_price purchase_invoice_line.unit_cost credit_note_line.unit_price
invoice_line.debit !ledger_semantics
invoice_line.credit !ledger_semantics
invoice_line.taxes !tax_semantics
invoice_line.net_amount sales_invoice_line.line_total purchase_invoice_line.line_total credit_note_line.line_total
payment.number !numbering_is_config
payment.party payment.customer payment.supplier
payment.amount payment.amount
payment.paid_on payment.posting_date
payment.direction payment.payment_type
payment.journal !ledger_semantics
payment.status !workflow_state
warehouse.name @location.labels
warehouse.code @location.id
warehouse.stock_location !stock_semantics
location.name !no_blueprint_entity
location.path !no_blueprint_entity
location.kind !no_blueprint_entity
location.parent !no_blueprint_entity
stock_level.item !stock_semantics
stock_level.location !stock_semantics
stock_level.quantity !stock_semantics
stock_level.reserved !stock_semantics
"""

# model | field | op | values (comma) | code. Counts matching records; a count above zero raises needs_human.
_RECORD_CHECKS = """
account.move | move_type | in | entry,out_receipt,in_receipt | journal_entry_not_mapped
account.move | state | in | posted | posted_entries
account.payment | state | in | posted,paid | posted_entries
"""

# neutral type -> Blueprint field types it can feed.
COMPAT = {
    "text": {"string", "text", "phone", "email"}, "integer": {"integer", "decimal"},
    "decimal": {"decimal", "money", "percent"}, "boolean": {"boolean"}, "date": {"date"},
    "datetime": {"date", "datetime"}, "enum": {"select"}, "reference": {"link", "select"},
    "binary": {"attachment"},
}
ENUM_REVIEW_TARGETS = frozenset({"select"})  # source values are never translated automatically


def _rows(text: str, cols: int) -> list:
    return [[c.strip() for c in ln.split("|")][:cols] for ln in text.strip().splitlines()]


MODELS: dict = {}
for _m, _k, _a, _h in (r + [""] * (4 - len(r)) for r in _rows(_MODELS, 4)):
    MODELS[_m] = {"kind": _k, "args": tuple(_a.split()), "human": _h}

FIELDS: dict = {}
FIELD_ORDER: dict = {}  # priority: first source field in table order wins a contested target
for _i, _ln in enumerate(_FIELDS.strip().splitlines()):
    _n, *_t = _ln.split()
    FIELDS[_n] = tuple(_t)
    FIELD_ORDER[_n] = _i

RECORD_CHECKS: list = [(m, f, tuple(v.split(",")), c) for m, f, _op, v, c in _rows(_RECORD_CHECKS, 5)]
