"""Blueprint validator entry point: schema step, then one function per x-validator-rule."""
from __future__ import annotations

from typing import Any, Callable

from .report import Report, ValidationContext
from .rules_branding import rule_assets, rule_contrast, rule_einvoicing, rule_white_label
from .rules_components import rule_components, rule_functions
from .rules_locale import rule_country, rule_locale
from .rules_refs import rule_references
from .rules_structure import rule_approvals, rule_i18n, rule_roles, rule_workflow
from .schema_step import load_schema, run_schema

RULES: list[tuple[str, Callable]] = [
    ("locale", rule_locale),            # x-validator-rules 1
    ("country", rule_country),          # 2
    ("references", rule_references),    # 3
    ("i18n", rule_i18n),                # 4
    ("workflow", rule_workflow),        # 5
    ("approvals", rule_approvals),      # 6
    ("roles", rule_roles),              # 7
    ("components", rule_components),    # 8
    ("functions", rule_functions),      # 9
    ("contrast", rule_contrast),        # 10
    ("assets", rule_assets),            # 11
    ("white_label", rule_white_label),  # 12
    ("einvoicing", rule_einvoicing),    # 13
]


def validate(blueprint: Any, ctx: ValidationContext | None = None) -> Report:
    """Validate a Blueprint. Never raises for bad input: any problem becomes an error in the Report (fail closed)."""
    rep = Report()
    try:
        schema = load_schema(ctx)
    except Exception as exc:  # unreadable or invalid contract file
        rep.error("BP-INTERNAL-001", "", f"cannot load blueprint schema: {type(exc).__name__}")
        return rep
    try:
        run_schema(blueprint, schema, rep)
    except Exception as exc:
        rep.error("BP-INTERNAL-001", "", f"schema validation failed to run: {type(exc).__name__}")
    if not isinstance(blueprint, dict):
        return rep
    for name, fn in RULES:
        try:
            fn(blueprint, ctx, rep)
        except Exception as exc:  # malformed shapes the rule did not anticipate
            rep.error("BP-INTERNAL-001", "", f"rule '{name}' could not run on this input ({type(exc).__name__})")
    return rep
