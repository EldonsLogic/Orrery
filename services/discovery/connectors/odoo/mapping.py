"""Data tables: the generic default model list for a trading business and the export mapping
(source model/field -> neutral intermediate name and type). NOT the Blueprint mapping (DSC-013).
Extend by adding lines; unmapped fields are reported, never dropped."""
from __future__ import annotations

DEFAULT_MODELS = (
    "res.company", "res.currency", "res.partner",
    "product.category", "product.template", "product.product", "uom.uom",
    "account.tax", "account.account", "account.journal",
    "sale.order", "sale.order.line", "purchase.order", "purchase.order.line",
    "account.move", "account.move.line", "account.payment",
    "stock.warehouse", "stock.location", "stock.quant",
)

# Odoo field type -> neutral type.
TYPE_MAP = {
    "char": "text", "text": "text", "html": "text", "integer": "integer", "float": "decimal",
    "monetary": "decimal", "boolean": "boolean", "date": "date", "datetime": "datetime",
    "selection": "enum", "many2one": "reference", "one2many": "reference_list",
    "many2many": "reference_list", "binary": "binary", "image": "binary", "reference": "reference",
    "many2one_reference": "reference", "json": "json", "properties": "json",
}
BINARY_TYPES = frozenset({"binary", "image"})

# model | field | neutral name | neutral type. Model `*` applies to every model.
_TABLE = """
* id record.source_id integer
* display_name record.label text
* create_date record.created_at datetime
* write_date record.updated_at datetime
* active record.active boolean
* company_id record.company reference
* currency_id record.currency reference
res.company name company.name text
res.company currency_id company.currency reference
res.company vat company.tax_number text
res.currency name currency.code text
res.currency symbol currency.symbol text
res.currency rounding currency.rounding decimal
res.partner name party.name text
res.partner ref party.code text
res.partner vat party.tax_number text
res.partner email party.email text
res.partner phone party.phone text
res.partner mobile party.mobile text
res.partner street party.address_line1 text
res.partner city party.city text
res.partner country_id party.country reference
res.partner is_company party.is_organisation boolean
res.partner customer_rank party.customer_rank integer
res.partner supplier_rank party.supplier_rank integer
res.partner parent_id party.parent reference
res.partner property_payment_term_id party.payment_terms reference
product.category name item_group.name text
product.category parent_id item_group.parent reference
product.template name item.name text
product.template default_code item.code text
product.template categ_id item.group reference
product.template type item.kind enum
product.template list_price item.sale_price decimal
product.template standard_price item.cost decimal
product.template uom_id item.unit reference
product.template taxes_id item.sale_taxes reference_list
product.template supplier_taxes_id item.purchase_taxes reference_list
product.template barcode item.barcode text
product.product default_code item.code text
product.product product_tmpl_id item.template reference
product.product barcode item.barcode text
product.product lst_price item.sale_price decimal
product.product standard_price item.cost decimal
uom.uom name unit.name text
uom.uom category_id unit.category reference
uom.uom factor unit.factor decimal
account.tax name tax.name text
account.tax amount tax.rate decimal
account.tax amount_type tax.computation enum
account.tax type_tax_use tax.scope enum
account.tax price_include tax.included_in_price boolean
account.account code ledger_account.code text
account.account name ledger_account.name text
account.account account_type ledger_account.kind enum
account.account reconcile ledger_account.reconcilable boolean
account.journal name journal.name text
account.journal code journal.code text
account.journal type journal.kind enum
account.journal default_account_id journal.default_account reference
sale.order name sales_order.number text
sale.order partner_id sales_order.customer reference
sale.order date_order sales_order.ordered_at datetime
sale.order state sales_order.status enum
sale.order amount_untaxed sales_order.net_total decimal
sale.order amount_tax sales_order.tax_total decimal
sale.order amount_total sales_order.gross_total decimal
sale.order order_line sales_order.lines reference_list
sale.order warehouse_id sales_order.warehouse reference
sale.order.line order_id sales_order_line.order reference
sale.order.line product_id sales_order_line.item reference
sale.order.line name sales_order_line.description text
sale.order.line product_uom_qty sales_order_line.quantity decimal
sale.order.line product_uom sales_order_line.unit reference
sale.order.line price_unit sales_order_line.unit_price decimal
sale.order.line discount sales_order_line.discount_percent decimal
sale.order.line tax_id sales_order_line.taxes reference_list
sale.order.line price_subtotal sales_order_line.net_amount decimal
purchase.order name purchase_order.number text
purchase.order partner_id purchase_order.supplier reference
purchase.order date_order purchase_order.ordered_at datetime
purchase.order state purchase_order.status enum
purchase.order amount_untaxed purchase_order.net_total decimal
purchase.order amount_tax purchase_order.tax_total decimal
purchase.order amount_total purchase_order.gross_total decimal
purchase.order order_line purchase_order.lines reference_list
purchase.order.line order_id purchase_order_line.order reference
purchase.order.line product_id purchase_order_line.item reference
purchase.order.line name purchase_order_line.description text
purchase.order.line product_qty purchase_order_line.quantity decimal
purchase.order.line price_unit purchase_order_line.unit_price decimal
purchase.order.line taxes_id purchase_order_line.taxes reference_list
purchase.order.line price_subtotal purchase_order_line.net_amount decimal
account.move name invoice.number text
account.move move_type invoice.kind enum
account.move partner_id invoice.party reference
account.move invoice_date invoice.issued_on date
account.move invoice_date_due invoice.due_on date
account.move state invoice.status enum
account.move payment_state invoice.payment_status enum
account.move amount_untaxed invoice.net_total decimal
account.move amount_tax invoice.tax_total decimal
account.move amount_total invoice.gross_total decimal
account.move journal_id invoice.journal reference
account.move invoice_line_ids invoice.lines reference_list
account.move.line move_id invoice_line.invoice reference
account.move.line account_id invoice_line.ledger_account reference
account.move.line product_id invoice_line.item reference
account.move.line name invoice_line.description text
account.move.line quantity invoice_line.quantity decimal
account.move.line price_unit invoice_line.unit_price decimal
account.move.line debit invoice_line.debit decimal
account.move.line credit invoice_line.credit decimal
account.move.line tax_ids invoice_line.taxes reference_list
account.move.line price_subtotal invoice_line.net_amount decimal
account.payment name payment.number text
account.payment partner_id payment.party reference
account.payment amount payment.amount decimal
account.payment date payment.paid_on date
account.payment payment_type payment.direction enum
account.payment journal_id payment.journal reference
account.payment state payment.status enum
stock.warehouse name warehouse.name text
stock.warehouse code warehouse.code text
stock.warehouse lot_stock_id warehouse.stock_location reference
stock.location name location.name text
stock.location complete_name location.path text
stock.location usage location.kind enum
stock.location location_id location.parent reference
stock.quant product_id stock_level.item reference
stock.quant location_id stock_level.location reference
stock.quant quantity stock_level.quantity decimal
stock.quant reserved_quantity stock_level.reserved decimal
"""


def _parse(table: str) -> dict:
    out: dict = {}
    for line in table.strip().splitlines():
        model, field, neutral, ntype = line.split()
        out.setdefault(model, {})[field] = (neutral, ntype)
    return out


MAPPING = _parse(_TABLE)


def lookup(model: str, field: str):
    """(neutral_name, neutral_type) for a source model/field, or None when unmapped."""
    return MAPPING.get(model, {}).get(field) or MAPPING["*"].get(field)
