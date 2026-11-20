"""The preview a user confirms. Built from the diff alone (no model prose); bilingual summary line is a template."""
from __future__ import annotations

import json
import unicodedata

from .models import MAX_PREVIEW_OPS, Preview, Proposal



def _ar(locale) -> bool:
    return str(locale).lower().startswith("ar")


def _esc(s: str) -> str:
    """Line breaks, control and bidi/format characters and backslashes are shown as escapes, so a drafted value can
    never fake a row or reorder the text: what is shown is exactly what is applied."""
    return "".join(ch if ch != "\\" and unicodedata.category(ch) not in ("Cc", "Cf", "Zl", "Zp", "Cs", "Co", "Cn")
                   else ("\\\\" if ch == "\\" else f"\\u{ord(ch):04x}" if ord(ch) < 0x10000 else f"\\U{ord(ch):08x}")
                   for ch in s)


def _clip(v, n=200):
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, sort_keys=True)
    return _esc(s if len(s) <= n else s[:n] + "...")


def build_preview(p: Proposal, locale: str = "en") -> Preview:
    ops = tuple({"code": o["code"], "impact": o["impact"], "subject": o["subject"], "property": o["property"],
                 "pointer": _esc(str(o["pointer"])), "op": o["op"], "before": _clip(o.get("before")),
                 "after": _clip(o.get("after")), "labels": o.get("labels")} for o in p.diff["ops"][:MAX_PREVIEW_OPS])
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
