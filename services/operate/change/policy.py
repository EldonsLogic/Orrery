"""What a chat change may touch, decided on the RESULTING DIFF (every changed path), never on the drafted edit.

Default deny: an op is allowed only if its schema path is on the explicit low-risk allow-list below (labels, option
labels, an added optional plain field or select option, a plain maxLength (lowering one needs review), non-assistant label overrides, branding
display name and colours). Before that, every op is checked for:
- the owning entity of the op (entity, workflow.entity, report.entity, the entity named by a label-override key, a link
  target), in the current and the target Blueprint: ledger class or a ledger/tax name -> `change_ledger_tax`, stock
  class -> risk R3 (refused above R2);
- tax tokens in a field id or a money field -> `change_ledger_tax`;
- forbidden keys anywhere in the path or in the before/after subtrees -> `change_forbidden_path`;
- any remove or reorder -> `change_needs_review` (Q-280: removals are R3).
Pure functions; no model, no I/O."""
from __future__ import annotations

from .edits import FORBIDDEN_KEYS, _deep_keys
from .errors import ChangeRefused

STOCK_RISK = "R3"
TAX_TOKENS = frozenset({"tax", "vat", "zakat", "excise", "withholding", "wht", "gst", "duty", "duties", "customs",
                        "zatca", "fatoora"})
LOC = "<locale>"   # one localized-text key, or the whole localized object when the pattern ends here
# (schema path pattern, allowed op kinds). "*" is a list element id or map key.
ALLOW = (
    (("entities", "*", "labels", LOC), {"add", "replace"}),
    (("entities", "*", "pluralLabels", LOC), {"add", "replace"}),
    (("entities", "*", "fields", "*", "labels", LOC), {"add", "replace"}),
    (("entities", "*", "fields", "*", "options", "*", "labels", LOC), {"add", "replace"}),
    (("entities", "*", "fields", "*", "options", "*"), {"add"}),
    (("entities", "*", "fields", "*"), {"add"}),
    (("entities", "*", "fields", "*", "maxLength"), {"add", "replace"}),
    (("workflows", "*", "labels", LOC), {"add", "replace"}),
    (("workflows", "*", "states", "*", "labels", LOC), {"add", "replace"}),
    (("workflows", "*", "transitions", "*", "actionLabels", LOC), {"add", "replace"}),
    (("reports", "*", "labels", LOC), {"add", "replace"}),
    (("locations", "*", "labels", LOC), {"add", "replace"}),
    (("locations", "*", "city"), {"add", "replace"}),
    (("i18n", "labelOverrides", "*", LOC), {"add", "replace"}),
    (("i18n", "glossary", "*", "translations", LOC), {"add", "replace"}),
    (("branding", "displayName", LOC), {"add", "replace"}),
    (("branding", "primaryColour"), {"add", "replace"}),
    (("branding", "accentColour"), {"add", "replace"}),
)
NEW_FIELD_KEYS = frozenset({"id", "type", "labels", "maxLength", "options", "required"})
NEW_FIELD_TYPES = frozenset({"string", "text", "integer", "decimal", "percent", "boolean", "date", "datetime", "select",
                             "phone", "email"})
EXTRA_FORBIDDEN = frozenset({"readOnly", "locksEditing", "workflow", "from", "to", "kind", "notify", "schedule",
                             "deliverTo", "channel", "default", "target", "unique", "numbering", "components",
                             "relations", "parent", "entity", "metrics", "filters"})


def _tokens(s) -> set:
    from toolapi.classify import tokens
    return set(tokens(s))


_NOT_TAX = frozenset({"syntax", "taxi", "taxis", "taxonomy", "august"})  # known false positives of the substring match


def _tax_like(s) -> bool:
    """Token match, plus the flattened id (`vatrate`, `zatcaflag`, `salesvatamt`): a tax token anywhere in it."""
    if not isinstance(s, str):
        return False
    if _tokens(s) & TAX_TOKENS:
        return True
    flat = "".join(ch for ch in s.casefold() if ch.isalnum())
    if flat in _NOT_TAX:
        return False
    return any(t in flat for t in TAX_TOKENS)  # fails closed: a token anywhere in the joined id


def _schema_path(op) -> tuple:
    sp = op.get("schemaPath")
    if not isinstance(sp, str) or not sp.startswith("/"):
        raise ChangeRefused("change_forbidden_path")
    return tuple(sp[1:].split("/"))


def _match(sp: tuple, pattern: tuple) -> bool:
    if pattern and pattern[-1] == LOC:
        head = pattern[:-1]
        if len(sp) == len(head):
            return _match(sp, head)
        return len(sp) == len(pattern) and _match(sp[:-1], head)
    return len(sp) == len(pattern) and all(p in ("*", s) for p, s in zip(pattern, sp))


def _by_id(items, key):
    for x in items or []:
        if isinstance(x, dict) and x.get("id") == key:
            return x
    return None


def _owning_entities(path, current, target) -> set:
    out = set()
    head = path[0] if path else None
    if head == "entities" and len(path) > 1:
        out.add(path[1])
    for doc in (current, target):
        if head in ("workflows", "reports") and len(path) > 1:
            node = _by_id(doc.get(head), path[1])
            if isinstance(node, dict) and isinstance(node.get("entity"), str):
                out.add(node["entity"])
        if head == "entities" and len(path) > 3 and path[2] == "fields":
            fld = _by_id((_by_id(doc.get("entities"), path[1]) or {}).get("fields"), path[3])
            if isinstance(fld, dict) and isinstance(fld.get("target"), str):
                out.add(fld["target"])
    if head == "i18n" and len(path) > 2 and path[1] == "labelOverrides":
        out.add(str(path[2]).split(".")[0])
    return out


def _field(doc, eid, fid):
    return _by_id((_by_id(doc.get("entities"), eid) or {}).get("fields"), fid)


def _check_entities(path, current, target) -> str:
    from toolapi.classify import default_entity_class
    risk = "R0"
    for eid in _owning_entities(path, current, target):
        cls, _ = default_entity_class(eid)
        if cls == "ledger" or _tax_like(eid):
            raise ChangeRefused("change_ledger_tax")
        if cls == "stock":
            risk = STOCK_RISK
    return risk


def _check_tax(path, op, current, target) -> None:
    ids = [s for s in path if isinstance(s, str)]
    if path[:1] == ("i18n",) and len(path) > 2:
        ids.append(path[2])
    for v in (op.get("before"), op.get("after")):
        if isinstance(v, dict):
            ids.append(v.get("id", ""))
    if any(_tax_like(s) for s in ids):
        raise ChangeRefused("change_ledger_tax")
    if path[:1] == ("entities",) and len(path) > 3 and path[2] == "fields" and "labels" not in path:
        for doc in (current, target):
            f = _field(doc, path[1], path[3])
            if isinstance(f, dict) and f.get("type") == "money":
                raise ChangeRefused("change_ledger_tax")
        after = op.get("after")
        if isinstance(after, dict) and after.get("type") == "money":
            raise ChangeRefused("change_ledger_tax")


def _check_keys(path, op) -> None:
    bad = FORBIDDEN_KEYS | EXTRA_FORBIDDEN
    keys = set(path)
    for v in (op.get("before"), op.get("after")):
        keys |= set(_deep_keys(v))
    if keys & bad:
        raise ChangeRefused("change_forbidden_path")


def _check_locked_field(path, current, target) -> None:
    """Only labels may change on a computed or read-only field."""
    if path[:1] != ("entities",) or len(path) < 5 or path[2] != "fields" or path[4] == "labels":
        return
    for doc in (current, target):
        f = _field(doc, path[1], path[3])
        if isinstance(f, dict) and (f.get("computed") or f.get("readOnly")):
            raise ChangeRefused("change_forbidden_path")


def _check_max_length(sp, op) -> None:
    """Raising a limit is harmless; lowering (or a non-number) can conflict with stored data: Studio review."""
    if sp[-1:] != ("maxLength",):
        return
    if op.get("op") == "add":  # unbounded -> bounded is a lowering too
        raise ChangeRefused("change_needs_review")
    if op.get("op") != "replace":
        return
    b, a = op.get("before"), op.get("after")
    ok = all(isinstance(x, int) and not isinstance(x, bool) for x in (a, b))
    if not ok or a < b:
        raise ChangeRefused("change_needs_review")


def _check_new_field(sp, op) -> None:
    if sp[-2:] != ("fields", "*") or len(sp) != 4:
        return
    v = op.get("after")
    if not isinstance(v, dict) or not set(v) <= NEW_FIELD_KEYS or v.get("type") not in NEW_FIELD_TYPES \
            or v.get("required", False) is not False:
        raise ChangeRefused("change_forbidden_path")


def check_diff(diff: dict, current: dict, target: dict) -> str:
    """Refuse anything off the allow-list; return the entity-class risk floor (R0 or R3)."""
    risk = "R0"
    ops = diff.get("ops") or []
    for op in ops:
        path = tuple(op.get("path") or ())
        if not path:
            raise ChangeRefused("change_forbidden_path")
        r = _check_entities(path, current, target)
        risk = r if r != "R0" else risk
        _check_tax(path, op, current, target)
    for op in ops:
        if op.get("op") not in ("add", "replace"):
            raise ChangeRefused("change_needs_review")  # remove, reorder: Studio review (Q-280)
    if risk != "R0":
        return risk
    for op in ops:
        path, sp, kind = tuple(op["path"]), _schema_path(op), op["op"]
        if path[:2] == ("i18n", "labelOverrides") and len(path) > 2 and str(path[2]).lower().startswith("assistants."):
            raise ChangeRefused("change_forbidden_path")
        if not any(_match(sp, pat) and kind in kinds for pat, kinds in ALLOW):
            raise ChangeRefused("change_forbidden_path")
        _check_keys(path, op)
        _check_locked_field(path, current, target)
        _check_new_field(sp, op)
        _check_max_length(sp, op)
    return risk
