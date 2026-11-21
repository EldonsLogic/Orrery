"""
Change engine: Frappe app registration.

Registers runtime policy enforcement, Hijri companion synchronization, the
business record event outbox, and the internal-only request guard.
No Desk UI assets, no branding, no landing-page routing (the product UI is a separate service).
"""

_RECORD_DOCTYPES = (
    "Customer",
    "Sales Order",
    "Sales Invoice",
    "Delivery Note",
    "Item",
    "Item Price",
    "Price List",
    "Warehouse",
    "Stock Entry",
    "Stock Entry Type",
    "Stock Reconciliation",
    "Account",
    "Journal Entry",
    "Fiscal Year",
    "Company",
    "Address",
    "Contact",
)
_RECORD_HOOK_METHODS = (
    "after_insert",
    "on_update",
    "on_submit",
    "on_cancel",
    "on_update_after_submit",
    "on_trash",
    "after_rename",
)

app_name = "change_engine"
app_title = "Change Engine"
app_publisher = "Orrery"
app_description = "Guarded configuration apply layer: DDL plan gate, audited deploy, rollback, runtime policies"
app_email = "dev@example.invalid"
app_license = "TBD"  # see docs/legal/checklist.md (licence decision pending)

# Fresh installs mark patches complete without running them. Create the tables
# before app model synchronization invokes document validation hooks.
before_install = "change_engine.patches.ce_sec_003_create_policy_tables.execute"

after_install = "change_engine.patches.erp_009_create_event_outbox.execute"

# ERP-020 / ADR-0016: headless engine. Deny every HTTP request unless it is on the internal
# allowlist (Desk, /login, website routes and unlisted API calls all get a plain 404).
before_request = ["change_engine.api.route_guard.enforce_internal_only"]

# Runtime policy enforcement on supported write paths (Desk, REST, background jobs).
# NOTE: runs for every DocType; the policy store fails closed on database errors.
doc_events = {
    "*": {
        "validate": [
            "change_engine.api.endpoints.enforce_runtime_policies_on_validate",
            "change_engine.i18n.hijri_fields.sync_companions",
        ],
        "before_submit": [
            "change_engine.api.endpoints.enforce_runtime_policies_on_submit",
            "change_engine.i18n.hijri_fields.sync_companions",
        ],
        "before_update_after_submit": [
            "change_engine.api.endpoints.enforce_runtime_policies_on_update_after_submit",
            "change_engine.i18n.hijri_fields.sync_companions",
        ],
    },
    **{
        doctype: {method: "change_engine.adapter.record_events.record_document_event"
                  for method in _RECORD_HOOK_METHODS}
        for doctype in _RECORD_DOCTYPES
    },
}

scheduler_events = {"all": ["change_engine.adapter.record_events.publish_pending"]}

# Jinja print-format helper for bilingual Arabic/English tax invoice rendering (ERP-007).
jinja = {
    "methods": [
        "change_engine.print_formats.bilingual_tax_invoice.render_frappe_sales_invoice_html",
    ]
}
