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

# Runtime policy enforcement on supported write paths (Desk, REST, background jobs).
# NOTE: runs for every DocType; policies are in-process only until CE-SEC-003 is fixed.
doc_events = {
    "*": {
        "validate": "change_engine.api.endpoints.enforce_runtime_policies_on_validate",
        "before_submit": "change_engine.api.endpoints.enforce_runtime_policies_on_submit",
        "before_update_after_submit": "change_engine.api.endpoints.enforce_runtime_policies_on_update_after_submit",
    }
}
