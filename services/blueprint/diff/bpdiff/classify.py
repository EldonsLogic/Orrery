"""Code-computed classification of one operation: stable code, impact, subject. No prose, no model.

Rules are documented in services/blueprint/diff/README.md and tested in tests/diff.
"""
from __future__ import annotations

import copy
from typing import Any

from .model import NOUN, ORDER_SIGNIFICANT, SPath, node_at, path_info, pointer, spath

IMPACTS = ("cosmetic", "config", "data_shape", "destructive", "compliance", "access", "branding")
_SEVERITY = ("destructive", "data_shape", "compliance", "access", "branding", "config", "cosmetic")

LABEL_KEYS = {"labels", "pluralLabels", "actionLabels", "city", "note", "reason", "description"}
ACCESS_KEYS = {"visibleToRoles", "allowedRoles", "hiddenFields", "readOnlyFields"}
COMPLIANCE_COMPANY = [("company", "country"), ("company", "vatNumber"), ("company", "crNumber"),
                      ("company", "locale", "currency"), ("company", "locale", "fiscalYear")]
META_COSMETIC = [("meta", "revision"), ("meta", "createdAt"), ("meta", "updatedAt")]
DESTRUCTIVE_NODES = {spath(p) for p in (
    "locations/*", "components/*", "entities/*", "entities/*/fields/*", "entities/*/fields/*/options/*",
    "entities/*/relations/*", "entities/*/components/*", "workflows/*", "workflows/*/states/*")}
DATA_FIELD_PROPS = {"type", "required", "unique", "precision", "min", "max", "maxLength", "target", "computed"}
SECTIONS = {"meta", "company", "compliance", "i18n", "branding"}
STEPS = spath("approvals/*/steps")
LABEL_FIELD = {"branding": "displayName", "company": "legalName", "glossary_term": "translations",
               "transition": "actionLabels"}


def _starts(sp: SPath, prefix: tuple) -> bool:
    return sp[:len(prefix)] == prefix


def _related(sp: SPath, prefix: tuple) -> bool:
    """sp is inside prefix, or is an ancestor of it (an op that replaces a whole parent)."""
    n = min(len(sp), len(prefix))
    return sp[:n] == prefix[:n]


def impact_of(kind: str, sp: SPath) -> str:
    if kind == "reorder":
        if sp == STEPS:
            return "access"
        return "config" if sp in ORDER_SIGNIFICANT else "cosmetic"
    head = sp[0] if sp else ""
    if head == "compliance" or any(_related(sp, p) for p in COMPLIANCE_COMPANY):
        return "compliance"
    if head == "branding":
        return "branding"
    if ("provenance" in sp or LABEL_KEYS & set(sp) or (head == "i18n" and not _starts(sp, ("i18n", "defaultLocale")))
            or any(_starts(sp, p) for p in META_COSMETIC)):
        return "cosmetic"
    if (head in ("roles", "approvals") or ACCESS_KEYS & set(sp)
            or (head == "workflows" and len(sp) >= 4 and sp[2] == "transitions"
                and (len(sp) == 4 or sp[4] == "approval"))):
        return "access"
    if kind == "remove" and sp in DESTRUCTIVE_NODES:
        return "destructive"
    if _data_shape(sp):
        return "data_shape"
    return "config"


def _data_shape(sp: SPath) -> bool:
    if sp[:1] != ("entities",):
        return False
    if len(sp) == 2:  # an entity itself
        return True
    if sp[2] == "kind":
        return True
    if sp[2] == "fields" and len(sp) >= 4:
        return len(sp) == 4 or sp[4] in DATA_FIELD_PROPS
    return sp[2] in ("relations", "components") and len(sp) >= 4


def _noun_code(kind: str) -> str:
    return kind.upper().replace("_", "-")


def _subject(path: tuple, elems: list, reorder: bool) -> tuple[dict, str, int | None]:
    """(subject, property, position of the subject node in path or None)."""
    if elems:
        i, noun, key = elems[-1]
        parents = [{"kind": n, "id": k} for _, n, k in elems[:-1]]
        return ({"kind": noun, "id": key, "parents": parents},
                "/".join(str(s) for s in path[i + 1:]), i)
    if path and path[0] in SECTIONS:
        return ({"kind": path[0], "id": None, "parents": []},
                "/".join(str(s) for s in path[1:]), 0)
    return {"kind": "blueprint", "id": None, "parents": []}, "/".join(str(s) for s in path), None


def _code(kind: str, sp: SPath, subj: dict, path: tuple, elems: list) -> str:
    noun = _noun_code(subj["kind"])
    if kind == "reorder":
        return f"BPD-{_noun_code(NOUN[sp + ('*',)])}-REORDERED"
    at_element = bool(elems) and elems[-1][0] == len(path) - 1
    if kind in ("add", "remove") and at_element:
        return f"BPD-{noun}-{'ADDED' if kind == 'add' else 'REMOVED'}"
    if sp[:1] == ("entities",) and len(sp) == 5 and sp[2] == "fields" and sp[4] in ("type", "required"):
        return f"BPD-FIELD-{sp[4].upper()}-CHANGED"
    if sp[:1] == ("branding",) and len(sp) == 2 and sp[1] in ("primaryColour", "accentColour"):
        return "BPD-BRANDING-COLOUR-CHANGED"
    if sp[:1] == ("roles",) and len(sp) >= 3 and sp[2] == "scope":
        return "BPD-ROLE-SCOPE-CHANGED"
    if LABEL_KEYS & set(sp) and elems:
        return f"BPD-{noun}-LABEL-CHANGED"
    return f"BPD-{noun}-CHANGED"


def labels_of(subject_path: tuple, kind: str, doc: Any) -> Any:
    node = node_at(doc, subject_path)
    if not isinstance(node, dict):
        return None
    lt = node.get(LABEL_FIELD.get(kind, "labels"))
    if isinstance(lt, dict) and lt and all(type(v) is str for v in lt.values()):
        return dict(lt)
    return None


def build_op(kind: str, path: tuple, before: Any = None, after: Any = None, index: int | None = None,
             labels: dict | None = None) -> dict:
    """Assemble one operation dict. `labels` is {"before": ..., "after": ...} or None."""
    sp, elems = path_info(path)
    subj, prop, _ = _subject(path, elems, kind == "reorder")
    op: dict[str, Any] = {
        "op": kind,
        "code": _code(kind, sp, subj, path, elems),
        "impact": impact_of(kind, sp),
        "pointer": pointer(path),
        "path": list(path),
        "schemaPath": "/" + "/".join(sp),
        "subject": subj,
        "property": prop,
    }
    if index is not None:
        op["index"] = index
    if kind in ("remove", "replace", "reorder"):
        op["before"] = copy.deepcopy(before)
    if kind in ("add", "replace", "reorder"):
        op["after"] = copy.deepcopy(after)
    if kind == "reorder":
        op["orderSignificant"] = sp in ORDER_SIGNIFICANT
    op["labels"] = labels
    return op


def subject_path(path: tuple) -> tuple[tuple, str]:
    """Path of the node whose labels describe the op, and its kind."""
    _, elems = path_info(path)
    if elems:
        return tuple(path[:elems[-1][0] + 1]), elems[-1][1]
    if path and path[0] in SECTIONS:
        return (path[0],), path[0]
    return (), "blueprint"


def make_labels(path: tuple, a: Any, b: Any) -> dict | None:
    sp_path, kind = subject_path(path)
    if not sp_path:
        return None
    before, after = labels_of(sp_path, kind, a), labels_of(sp_path, kind, b)
    if before is None and after is None:
        return None
    return {"before": before, "after": after}


def risk_of(ops: list[dict]) -> dict:
    counts = {i: 0 for i in IMPACTS}
    for op in ops:
        counts[op["impact"]] += 1
    top = next((i for i in _SEVERITY if counts[i]), None)
    return {
        "counts": counts,
        "total": len(ops),
        "maxImpact": top,
        "needsDdlPlanGate": bool(counts["data_shape"] or counts["destructive"]),
        "touchesCompliance": bool(counts["compliance"]),
        "touchesAccess": bool(counts["access"]),
    }


def summary_of(ops: list[dict]) -> dict:
    s = {"add": 0, "remove": 0, "replace": 0, "reorder": 0}
    for op in ops:
        s[op["op"]] += 1
    return s
