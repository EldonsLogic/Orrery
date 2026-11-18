"""Classification rules shared by the generator and the checker. Pure; data comes from policy.py.

Every rule here fails closed: an unknown entity is refused, a name token only adds restriction, a registry only raises.
`default_entity_class` is the single point to replace when the reviewed component manifest supplies the entity class.
"""
from __future__ import annotations

import hashlib
import re

from . import policy as P
from .result import Issue, canonical

_CAMEL = re.compile(r"([a-z0-9])([A-Z])")
_SPLIT = re.compile(r"[^a-z0-9]+")
_SOURCE = re.compile(r"^[a-z0-9][a-z0-9_.:/-]{0,127}$")
_RANK = {r: i for i, r in enumerate(P.RISK_ORDER)}


def tokens(name) -> list[str]:
    """`approvedBy`, `approved_by` and `approved-by` all give ["approved", "by"]."""
    return [t for t in _SPLIT.split(_CAMEL.sub(r"\1_\2", str(name)).lower()) if t]


def _has_phrase(toks: list[str], phrases) -> bool:
    return any((a, b) in phrases for a, b in zip(toks, toks[1:]))


def class_max(a: str | None, b: str | None) -> str | None:
    if a is None or b is None:
        return a or b
    return a if P.CLASS_RANK[a] >= P.CLASS_RANK[b] else b


# ---- entities --------------------------------------------------------------------------------------------------------
def default_entity_class(eid: str) -> tuple[str | None, str | None]:
    """-> (class, basis). basis is "table" or "name_token"; (None, None) means no reviewed class: refuse."""
    if eid in P.ENTITY_CLASS_DEFAULTS:
        return P.ENTITY_CLASS_DEFAULTS[eid], "table"
    if set(tokens(eid)) & P.LEDGER_NAME_TOKENS:
        return "ledger", "name_token"
    return None, None


def identity_entity(eid: str) -> bool:
    return str(eid).startswith(P.IDENTITY_ENTITY_PREFIXES) or bool(set(tokens(eid)) & P.IDENTITY_ENTITY_TOKENS)


# ---- arguments and fields --------------------------------------------------------------------------------------------
def forbidden_arg(name) -> bool:
    if name in P.ARG_NAME_ALLOW:
        return False
    toks = tokens(name)
    flat = str(name).lower().replace("_", "").replace("-", "")
    return (bool(set(toks) & P.FORBIDDEN_ARG_TOKENS) or flat in P.FORBIDDEN_ARG_NAMES
            or _has_phrase(toks, P.FORBIDDEN_ARG_PHRASES))


def sensitivity(name, field_type=None, target=None) -> str | None:
    """Sensitivity class of a field or relation from its id, its type and its link target, or None."""
    hits = set()
    for n in (name, target):
        if n is None:
            continue
        toks = tokens(n)
        for cls in P.SENSITIVE_CLASSES:
            if set(toks) & P.SENSITIVE_TOKENS[cls] or _has_phrase(toks, P.SENSITIVE_PHRASES[cls]):
                hits.add(cls)
    if field_type in P.SENSITIVE_FIELD_TYPES:
        hits.add(P.SENSITIVE_FIELD_TYPES[field_type])
    return next((c for c in P.SENSITIVE_CLASSES if c in hits), None)


PHONE_PATTERN = "^\\+?[0-9 ()-]{5,20}$"  # schema.py emits this for phone fields


def schema_sensitivity(name, schema) -> str | None:
    """Checker side: the same rule, read from a generated property schema."""
    s = schema if isinstance(schema, dict) else {}
    ftype = "email" if s.get("format") == "email" else "phone" if s.get("pattern") == PHONE_PATTERN else None
    hit = sensitivity(name, ftype, s.get("x-entity-ref"))
    if hit is None and isinstance(s.get("items"), dict):
        hit = sensitivity(name, None, s["items"].get("x-entity-ref"))
    return hit or (s.get("x-sensitive") if s.get("x-sensitive") in P.SENSITIVE_CLASSES else None)


def status_like(fid: str, has_workflow: bool) -> bool:
    return fid in P.ENGINE_STATUS_FIELDS or (has_workflow and bool(set(tokens(fid)) & P.WORKFLOW_STATUS_TOKENS))


# ---- transitions -----------------------------------------------------------------------------------------------------
def transition_kind(tid: str, cls: str, from_kind: str | None, to_id: str, to_kind: str | None,
                    approval_step: bool, declared: str | None = None) -> tuple[str, bool]:
    """-> (kind, agent_forbidden). Candidates are collected and the riskiest wins; tokens only ever add a candidate.

    `declared` is an explicit kind; it replaces only the structural rule for stock and ledger entities.
    """
    toks = tokens(tid)
    ts = set(toks)
    from_initial = from_kind == "initial"
    to_cancel = bool(set(tokens(to_id)) & P.CANCEL_STATE_TOKENS)
    cands: set[str] = set()
    if ts & P.APPROVE_TOKENS or _has_phrase(toks, P.APPROVE_PHRASES):
        cands.add("approve")
    if ts & P.REJECT_TOKENS:
        cands.add("reject")
    rev = bool(ts & P.REVERSAL_TOKENS) or _has_phrase(toks, P.REVERSAL_PHRASES)
    if ts & P.CANCEL_TOKENS or rev or to_cancel:
        if from_initial and to_cancel:
            cands.add("cancel_draft")
        elif from_initial:  # named like a cancel but it does not go to a cancel state: at least an advance
            cands |= {"cancel_draft", "advance"}
        else:
            cands.add("reversal" if rev else "cancel")
    if declared is not None:
        cands.add("cancel_draft" if declared == "cancel" and from_initial and to_cancel else declared)
    elif cls in ("stock", "ledger"):
        if approval_step:
            cands.add("approve")
        if not from_initial:
            cands.add("reversal")
        if to_kind == "final" and not (from_initial and to_cancel):
            cands.add("reversal")
    if not cands:
        cands.add("advance")
    order = {k: i for i, k in enumerate(P.KIND_PRECEDENCE)}
    kind = max(cands, key=lambda k: (_RANK[P.RISK[cls][k]], -order[k]))
    return kind, bool(cands & P.AGENT_FORBIDDEN_KINDS)


# ---- policy with an optional L0 registry -----------------------------------------------------------------------------
class Policy:
    """Built-in classes and effects merged with an optional L0 registry, which may only raise them."""

    def __init__(self, registry):
        self.errors: list[Issue] = []
        self.reg_classes: dict[str, str] = {}
        self.reg_effects: dict[str, dict] = {}
        self.meta = None
        reg = registry if registry is not None else {}
        if not isinstance(reg, dict) or set(reg) - {"source", "entity_classes", "entity_effects"}:
            self._err("TAPI-REGISTRY-001", "/registry", "registry must be a mapping with only source, entity_classes and entity_effects")
            return
        if not reg:
            return
        src = reg.get("source")
        if not isinstance(src, str) or not _SOURCE.match(src):
            self._err("TAPI-REGISTRY-001", "/registry/source", "registry must name its L0 configuration source")
        classes, effects = reg.get("entity_classes") or {}, reg.get("entity_effects") or {}
        if not isinstance(classes, dict) or not isinstance(effects, dict):
            self._err("TAPI-REGISTRY-001", "/registry", "entity_classes and entity_effects must be mappings")
            return
        for k, c in sorted(classes.items()):
            base, _ = default_entity_class(k)
            if c not in P.ENTITY_CLASSES:
                self._err("TAPI-REGISTRY-001", f"/registry/entity_classes/{k}", f"unknown entity class {c!r}")
            elif base is not None and P.CLASS_RANK[c] < P.CLASS_RANK[base]:
                self._err("TAPI-REGISTRY-002", f"/registry/entity_classes/{k}", f"registry may not lower {k!r} from {base} to {c}")
            else:
                self.reg_classes[k] = c
        for k, v in sorted(effects.items()):
            if not isinstance(v, dict) or set(v) - set(P.EFFECT_KEYS) or any(not isinstance(x, bool) for x in v.values()):
                self._err("TAPI-REGISTRY-001", f"/registry/entity_effects/{k}", "effects must be booleans for ledger, tax, external_send")
                continue
            base = P.ENTITY_EFFECT_DEFAULTS.get(k, {})
            if any(base.get(x) and v.get(x) is False for x in P.EFFECT_KEYS):
                self._err("TAPI-REGISTRY-002", f"/registry/entity_effects/{k}", f"registry may not remove a built-in effect of {k!r}")
                continue
            self.reg_effects[k] = dict(v)
        self.meta = {"source": src, "sha256": "sha256:" + hashlib.sha256(canonical(reg).encode("utf-8")).hexdigest()}

    def _err(self, code, ptr, fact):
        self.errors.append(Issue(code, ptr, fact))

    def entity_class(self, eid: str) -> str | None:
        return class_max(default_entity_class(eid)[0], self.reg_classes.get(eid))

    def effects(self, eid: str, cls: str, write: bool) -> dict:
        eff = {k: False for k in P.EFFECT_KEYS}
        if write:
            eff["ledger"] = cls in ("stock", "ledger")
            for src in (P.ENTITY_EFFECT_DEFAULTS.get(eid, {}), self.reg_effects.get(eid, {})):
                for k, v in src.items():
                    eff[k] = eff[k] or v
        return eff
