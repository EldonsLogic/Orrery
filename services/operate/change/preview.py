"""The preview a user confirms. Built from the diff alone (no model prose); bilingual summary line is a template."""
from __future__ import annotations

import json

from .models import Preview, Proposal

_MAX_OPS = 50


def _ar(locale) -> bool:
    return str(locale).lower().startswith("ar")


def _clip(v, n=200):
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, sort_keys=True)
    return s if len(s) <= n else s[:n] + "..."


def build_preview(p: Proposal, locale: str = "en") -> Preview:
    ops = tuple({"code": o["code"], "impact": o["impact"], "subject": o["subject"], "property": o["property"],
                 "pointer": o["pointer"], "op": o["op"], "before": _clip(o.get("before")),
                 "after": _clip(o.get("after")), "labels": o.get("labels")} for o in p.diff["ops"][:_MAX_OPS])
    risk = p.diff["risk"]
    n = len(p.diff["ops"])
    if _ar(locale):
        text = f"سيتم تطبيق {n} تغيير على الإعدادات. قل \"نعم\" للتأكيد خلال مدة محدودة."
    else:
        text = f"{n} change(s) to your configuration. Say \"yes\" to confirm, within the time limit."
    return Preview(p.action_id, p.digest, p.risk, p.expires_at, ops, dict(risk["counts"]), bool(risk["needsDdlPlanGate"]),
                   text, locale)


def applied_text(n: int, locale: str) -> str:
    return f"تم تطبيق {n} تغيير." if _ar(locale) else f"Applied {n} change(s)."
