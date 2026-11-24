"""
Change engine: Frappe app registration.

Registers only what the engine needs: runtime policy enforcement on document lifecycle events.
No Desk UI assets, no branding, no landing-page routing (the product UI is a separate service).
"""

app_name = "change_engine"
app_title = "Change Engine"
app_publisher = "Orrery"
app_description = "Guarded configuration apply layer: DDL plan gate, audited deploy, rollback, runtime policies"
app_email = "dev@example.invalid"
app_license = "TBD"  # see docs/legal/checklist.md (licence decision pending)

# Fresh installs mark patches complete without running them. Create the tables
# before app model synchronization invokes document validation hooks.
before_install = "change_engine.patches.ce_sec_003_create_policy_tables.execute"

# Runtime policy enforcement on supported write paths (Desk, REST, background jobs).
# NOTE: runs for every DocType; the policy store fails closed on database errors.
doc_events = {
    "*": {
        "validate": "change_engine.api.endpoints.enforce_runtime_policies_on_validate",
        "before_submit": "change_engine.api.endpoints.enforce_runtime_policies_on_submit",
        "before_update_after_submit": "change_engine.api.endpoints.enforce_runtime_policies_on_update_after_submit",
    }
}

# Jinja print-format helper for bilingual Arabic/English tax invoice rendering (ERP-007).
jinja = {
    "methods": [
        "change_engine.print_formats.bilingual_tax_invoice.render_frappe_sales_invoice_html",
    ]
}
