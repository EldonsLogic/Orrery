"""Coded refusals (fail closed) and the reason codes of the mapping report. Messages carry the code
and a key, never customer data. Reason keys are i18n keys; the UI owns the wording."""
from __future__ import annotations

ERRORS = {
    "BMP-E01": "bmp.err.input_shape",
    "BMP-E02": "bmp.err.too_large",
    "BMP-E03": "bmp.err.template_unreadable",
    "BMP-E04": "bmp.err.table_target_unresolved",
}

REASONS = (
    "no_blueprint_home", "no_blueprint_entity", "no_neutral_name", "invalid_name", "model_unavailable",
    "bookkeeping", "implicit_parent_link", "numbering_is_config", "workflow_state", "variant_structure",
    "semantic_mismatch", "binary_not_fetched", "tax_semantics", "ledger_semantics", "stock_semantics",
    "posted_entries", "journal_entry_not_mapped", "invoice_routing", "partner_role_split",
    "enum_values_review", "label_locale_unverified", "invalid_value",
    "type_mismatch", "target_taken", "duplicate_id", "used_for_routing",
)
REASON_KEYS = {r: f"bmp.reason.{r}" for r in REASONS}

# Reasons that always also need a person (rigid zone, ADR-0027 and principle 3, or an unverifiable guess).
HUMAN_REASONS = frozenset({"tax_semantics", "ledger_semantics", "stock_semantics", "posted_entries",
                           "journal_entry_not_mapped"})


class BlueprintMapError(Exception):
    def __init__(self, code: str, detail: str = ""):
        self.code = code
        self.key = ERRORS[code]
        self.detail = detail  # a limit or field name, never record content
        super().__init__(f"{code} {self.key}" + (f" ({detail})" if detail else ""))
