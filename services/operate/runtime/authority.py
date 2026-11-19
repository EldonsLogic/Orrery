"""ADR-0043 assistant restrictions, enforced at call time (the Blueprint validator checks them again at publish time).

An assistant call is an agent-class call with the invoking user's permissions. The model picks the tool and the
`transition_id` at call time, so the runtime refuses, whatever the config says: approve, reject, submit, cancel,
amend and delete verbs, protected tools, writes on ledger- or stock-class entities other than create, update and
export, and any transition that is not on the assistant's own list, is an approve, reject, cancel or reversal move,
or has its own approval rule. Sets mirror services/blueprint/validator/rules_assistants.py; keep them in step."""
from __future__ import annotations

import re

NEVER_TOOLS = frozenset({"approval.decide", "blueprint.propose_change"})
NEVER_DOMAINS = frozenset({"blueprint", "approval_rule", "role", "permission", "grant", "agent", "assistant"})
NEVER_VERBS = frozenset({"approve", "reject", "submit", "cancel", "amend", "delete", "update_bank_details",
                         "update_contact_details", "update_access"})
POSTING_ENTITY_VERBS = frozenset({"get", "list", "create", "update", "export"})
POSTING_CLASSES = frozenset({"ledger", "stock"})
POSTING_NAME_TOKENS = frozenset({
    "invoice", "invoices", "bill", "bills", "receipt", "receipts", "voucher", "vouchers", "entry", "entries",
    "payment", "payments", "payroll", "ledger", "journal", "salary", "payslip", "expense", "expenses", "refund",
    "credit", "debit", "tax", "vat", "depreciation", "settlement", "remittance", "payout", "disbursement", "cheque",
    "pos", "stock", "inventory", "delivery", "shipment", "dispatch", "transfer", "adjustment", "reconciliation",
    "closing", "accrual", "provision", "cash"})
NEVER_TRANSITION_KINDS = frozenset({"approve", "reject", "reversal", "cancel", "cancel_draft"})
NEVER_TRANSITION_TOKENS = frozenset({
    "approve", "approved", "approval", "authorise", "authorize", "authorised", "authorized", "accept", "accepted",
    "confirm", "confirmed", "release", "released", "signoff", "reject", "rejected", "decline", "declined", "deny",
    "denied", "void", "voided", "reverse", "reversed", "reversal", "refund", "refunded", "return", "returned",
    "amend", "amended", "writeoff", "unpost", "reopen", "undo", "rollback", "cancel", "cancelled", "canceled",
    "submit", "delete"})
_PHRASES = {("sign", "off"), ("write", "off"), ("written", "off")}
_SPLIT = re.compile(r"[^a-z0-9]+")


def _tokens(name: str) -> list:
    return [t for t in _SPLIT.split(re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name).lower()) if t]


def posting_entity(tool_def: dict, domain: str) -> bool:
    """Ledger or stock class from the generated tool (`entity_class`), else by name; unknown never means plain."""
    cls = tool_def.get("entity_class")
    if isinstance(cls, str) and cls in ("plain", "ledger", "stock"):
        return cls in POSTING_CLASSES or bool(set(_tokens(domain)) & POSTING_NAME_TOKENS)
    return True if tool_def.get("kind") not in ("read", None) else bool(set(_tokens(domain)) & POSTING_NAME_TOKENS)


def tool_refusal(name: str, tool_def: dict) -> str | None:
    """Reason an assistant may never call this tool, or None."""
    domain, _, verb = name.partition(".")
    if name in NEVER_TOOLS or domain in NEVER_DOMAINS or verb in NEVER_VERBS:
        return "assistant_forbidden"
    if verb not in POSTING_ENTITY_VERBS and posting_entity(tool_def, domain):
        return "assistant_posting"
    return None


def transition_refusal(tid: str, t: dict, listed: tuple) -> str | None:
    """Reason an assistant may never make this move, or None. `listed` is the assistant's own allow-list."""
    if tid not in listed:
        return "transition_not_listed"
    toks = _tokens(tid)
    if (t.get("kind") in NEVER_TRANSITION_KINDS or set(toks) & NEVER_TRANSITION_TOKENS
            or any(p in _PHRASES for p in zip(toks, toks[1:]))):
        return "assistant_forbidden"
    appr = t.get("approval")
    if t.get("approval_step") or (isinstance(appr, dict) and (appr.get("required") or appr.get("rules"))):
        return "assistant_forbidden"  # a move with its own approval rule
    return None
