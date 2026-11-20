"""Structural scope policy for AI-drafted components (H1 to H3 of the PR 216 review).

The control is not a word list. The risk class of every entity is DERIVED here from the reviewed Tool API tables
(services/operate/toolapi/policy.py and classify.py, shared, not copied); a model-supplied class is only ever compared
with it. Default deny: an entity, workflow or report is allowed only when its class is derived as plain, either from
the reviewed table or from an allow-list of benign scope words with no restricted word. Unknown never means plain.
The keyword scan in text.py stays as a backstop for prose.
"""
from __future__ import annotations

import sys
from pathlib import Path

_OPERATE = str(Path(__file__).resolve().parents[2] / "operate")
if _OPERATE not in sys.path:
    sys.path.insert(0, _OPERATE)

from toolapi import classify as _C  # noqa: E402
from toolapi import policy as _P  # noqa: E402

from .text import fold, scope_hits, tokens  # noqa: E402

# Artifact kinds an AI draft may provide. role_template, function, notification, event, workflow, metric, tool and
# scheduled_job are code, permission, approval or external-send surfaces (ADR-0048 items 4, 7, 12): human-built only.
ALLOWED_ARTIFACTS = ("entity", "screen", "report", "print_format")
# Benign scope words. A need that is not in the reviewed plain table must name at least one of these and no restricted word.
BENIGN_TOKENS = frozenset({
    "quote", "quotation", "lead", "opportunity", "project", "task", "ticket", "visit", "appointment", "booking", "survey",
    "checklist", "note", "notes", "category", "tag", "tags", "campaign", "inspection", "complaint", "feedback", "rating",
    "loyalty", "territory", "route", "document", "attachment", "reminder", "schedule", "announcement", "training", "course",
    "skill", "meeting", "equipment", "maintenance", "warranty", "visitor", "form", "template", "catalog", "wishlist", "comment",
})
RESTRICTED_TOKENS = frozenset(_P.LEDGER_NAME_TOKENS) | frozenset(_P.IDENTITY_ENTITY_TOKENS)
# Tenant role templates only: never the platform's own roles (the reviewer roles, admins, services, agents).
PLATFORM_ROLE_TOKENS = frozenset({"platform", "admin", "administrator", "reviewer", "superuser", "system", "root", "owner",
                                  "service", "agent", "assistant", "component", "factory", "approver", "auditor"})


def identifier_hits(name: str) -> list[str]:
    """Restricted words in an identifier (capability, artifact ref, field, test id, i18n key)."""
    toks = set(tokens(name))
    return sorted(toks & RESTRICTED_TOKENS) + scope_hits(name)


def derive_class(kind: str, ref: str) -> tuple[str | None, str]:
    """-> (class, reason). class is "plain" only when allowed; None means refuse and reason says why (a stable word)."""
    if _C.identity_entity(ref) or set(tokens(ref)) & set(_P.IDENTITY_ENTITY_TOKENS):
        return None, "identity_domain"
    hits = identifier_hits(ref)
    flat = "".join(tokens(ref))
    if kind == "entity":
        table = _P.ENTITY_CLASS_DEFAULTS.get(ref) or _P.ENTITY_CLASS_DEFAULTS.get("_".join(tokens(ref)))
        if table in ("stock", "ledger"):
            return None, f"reviewed_{table}"
        if hits:
            return None, "restricted_word"
        if _C.sensitivity(ref):
            return None, "sensitive"
        if table == "plain":
            return "plain", "reviewed_table"
    elif hits or _C.sensitivity(ref):
        return None, "restricted_word"
    if not (set(tokens(ref)) & BENIGN_TOKENS) or not flat:
        return None, "unclassified"
    return "plain", "benign_scope"


def platform_role(role: str) -> bool:
    return bool(set(tokens(role)) & (PLATFORM_ROLE_TOKENS | RESTRICTED_TOKENS))


def manifest_all_plain(m: dict) -> bool:
    """True when every entity a library manifest provides derives as plain (used to allow a `requires` on it)."""
    for p in m.get("provides", []) if isinstance(m, dict) else []:
        if not isinstance(p, dict) or identifier_hits(str(p.get("capability", ""))):
            return False
        for a in p.get("artifacts", []):
            if not isinstance(a, dict) or a.get("type") not in ALLOWED_ARTIFACTS:
                return False
            if derive_class(str(a.get("type")), str(a.get("ref", "")).split("/")[-1])[0] != "plain":
                return False
    return True
