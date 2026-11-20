"""Structural scope policy for AI-drafted components (PR 216 review: H1 to H3, then N1 and N4).

Names never prove a component is plain. The decision is structural and has three outcomes:
  refuse    a firm no: reviewed ledger or stock entity, identity domain, sensitive data, or a restricted word (the
            normalised word lists are a secondary deny signal only, not the control);
  plain     PROVEN: every word of the name is in the benign vocabulary and every field is of an allow-listed
            non-financial type (see PLAIN_FIELD_TYPES), links point at plain entities;
  unproven  anything else. It is not refused as forbidden: it is parked as `needs_human_classification`. A verified human
            attests the class; a human can never attest `plain` for a draft with a money-typed field.
The risk class is never taken from the model, and the reviewed Tool API tables (services/operate/toolapi) decide first.
"""
from __future__ import annotations

import sys
from pathlib import Path

_OPERATE = str(Path(__file__).resolve().parents[2] / "operate")
if _OPERATE not in sys.path:
    sys.path.insert(0, _OPERATE)

from toolapi import classify as _C  # noqa: E402
from toolapi import policy as _P  # noqa: E402

from .text import scope_hits, sensitive_hits, stems, tokens  # noqa: E402

# Artifact kinds an AI draft may provide. role_template, function, notification, event, workflow, metric, tool and
# scheduled_job are code, permission, approval or external-send surfaces (ADR-0048 items 4, 7, 12): human-built only.
ALLOWED_ARTIFACTS = ("entity", "screen", "report", "print_format")
# Field types that carry no money. Everything else (integer, decimal, percent, money, boolean ...) is unproven.
PLAIN_FIELD_TYPES = frozenset({"text", "long_text", "date", "datetime", "select", "checkbox", "link", "attachment"})
MONEY_FIELD_TYPES = frozenset({"money", "decimal", "percent", "currency", "quantity", "rate", "amount"})
SHAPE_FIELD_TYPES = PLAIN_FIELD_TYPES | MONEY_FIELD_TYPES | {"integer", "boolean"}
BENIGN_TOKENS = frozenset({
    "quote", "quotation", "lead", "opportunity", "project", "task", "ticket", "visit", "appointment", "booking", "survey",
    "checklist", "note", "notes", "category", "tag", "tags", "campaign", "inspection", "complaint", "feedback", "rating",
    "loyalty", "territory", "route", "document", "attachment", "reminder", "schedule", "announcement", "training", "course",
    "skill", "meeting", "equipment", "maintenance", "warranty", "visitor", "form", "template", "catalog", "wishlist", "comment",
})
# Neutral words that may sit beside a benign word (plus the words of the reviewed plain table, added below).
NEUTRAL_TOKENS = frozenset({"list", "type", "status", "item", "line", "detail", "result", "name", "group", "request", "slot",
                            "preference", "history", "record", "plan", "step", "answer", "question", "photo", "region"})
# Money movement and value words, secondary deny (stems): the structure decides, these only add a refusal.
MONEYISH_TOKENS = frozenset({
    "deposit", "wallet", "cashback", "prepayment", "loan", "advance", "commission", "allowance", "overtime", "bonus",
    "compensation", "fee", "charge", "cost", "receivable", "payable", "till", "cashbox", "refund", "payout", "settlement",
    "amount", "price", "balance", "currency", "total", "wage", "stipend", "reward", "discount", "rebate", "penalty", "fine",
    "invoice", "bill", "payment", "cash", "credit", "debit", "gl", "user", "sar", "aed", "egp", "qar",
})
RESTRICTED_TOKENS = frozenset(_P.LEDGER_NAME_TOKENS) | frozenset(_P.IDENTITY_ENTITY_TOKENS) | MONEYISH_TOKENS
_PLAIN_VOCAB = BENIGN_TOKENS | NEUTRAL_TOKENS | frozenset(t for e in _P.KNOWN_PLAIN for t in tokens(e))
# Tenant role templates only: never the platform's own roles (the reviewer roles, admins, services, agents).
PLATFORM_ROLE_TOKENS = frozenset({"platform", "admin", "administrator", "reviewer", "superuser", "system", "root", "owner",
                                  "service", "agent", "assistant", "component", "factory", "approver", "auditor"})


def _stemmed(name: str) -> set[str]:
    return {s for t in tokens(name) for s in stems(t)}


def identifier_hits(name: str) -> list[str]:
    """Restricted words in an identifier (capability, artifact ref, field, test id, i18n key): the secondary deny list."""
    return sorted(_stemmed(name) & RESTRICTED_TOKENS) + scope_hits(name) + sensitive_hits(name)


def classify(kind: str, ref: str) -> tuple[str, str]:
    """-> (verdict, why). verdict is "refuse", "plain" (proven) or "unproven" (a human must classify). Default is not plain."""
    toks = tokens(ref)
    if _C.identity_entity(ref) or _stemmed(ref) & set(_P.IDENTITY_ENTITY_TOKENS) or "user" in _stemmed(ref):
        return "refuse", "identity_domain"
    table = _P.ENTITY_CLASS_DEFAULTS.get(ref) or _P.ENTITY_CLASS_DEFAULTS.get("_".join(toks))
    if table in ("stock", "ledger"):
        return "refuse", f"reviewed_{table}"
    if sensitive_hits(ref) or _C.sensitivity(ref):
        return "refuse", "sensitive"
    if identifier_hits(ref):
        return "refuse", "restricted_word"
    if table == "plain":
        return "plain", "reviewed_table"
    stem_sets = [stems(t) for t in toks]
    if toks and all(s & _PLAIN_VOCAB for s in stem_sets) and any(s & BENIGN_TOKENS for s in stem_sets):
        return "plain", "benign_scope"
    return "unproven", "not_all_benign"


def derive_class(kind: str, ref: str) -> tuple[str | None, str]:
    """Compatibility view: "plain" only when proven, else None."""
    v, why = classify(kind, ref)
    return ("plain" if v == "plain" else None), why


def field_verdict(entity_targets: set[str], f: dict) -> tuple[str, str]:
    """Verdict for one drafted field: name, type, options and link target all count."""
    if sensitive_hits(f["name"]) or _C.sensitivity(f["name"], f["type"]) or identifier_hits(f["name"]):
        return "refuse", "field_name"
    if f["type"] in MONEY_FIELD_TYPES:
        return "unproven", "money_field"
    if f["type"] not in PLAIN_FIELD_TYPES:
        return "unproven", "field_type"
    if f["type"] == "link":
        tgt = f.get("target")
        if tgt not in entity_targets:
            v, _ = classify("entity", tgt) if isinstance(tgt, str) else ("unproven", "link_target")
            if v != "plain":
                return v, "link_target"
    if f["type"] == "select" and not (isinstance(f.get("options"), list) and f["options"]):
        return "unproven", "open_select"
    return "plain", "allow_listed_type"


def platform_role(role: str) -> bool:
    return bool(_stemmed(role) & (PLATFORM_ROLE_TOKENS | RESTRICTED_TOKENS))


def manifest_all_plain(m: dict) -> bool:
    """True when every artifact a library manifest provides is provably plain (used to allow a `requires` on it)."""
    for p in m.get("provides", []) if isinstance(m, dict) else []:
        if not isinstance(p, dict) or identifier_hits(str(p.get("capability", ""))):
            return False
        for a in p.get("artifacts", []):
            if not isinstance(a, dict) or a.get("type") not in ALLOWED_ARTIFACTS:
                return False
            if classify(str(a.get("type")), str(a.get("ref", "")).split("/")[-1])[0] != "plain":
                return False
    return True
