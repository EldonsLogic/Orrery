"""Question catalog loaded from the template's questions.json, plus per-type value validation."""
from __future__ import annotations

import importlib.util
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

DISCOVERY = Path(__file__).resolve().parents[1]
DEFAULT_QUESTIONS = DISCOVERY / "templates" / "trading-distribution" / "questions.json"
INSTANTIATE = DISCOVERY / "templates" / "instantiate.py"
MAX_TEXT = 200
# Per-question numeric bounds (inclusive). Placeholders; a bound only rejects nonsense input.
BOUNDS = {"q_branches": (1, 50), "q_customer_terms": (0, 365), "q_supplier_terms": (0, 365),
          "q_discount_threshold": (0, 100)}
DEFAULT_BOUNDS = (0, 10 ** 12)
SIMPLE_CODE = re.compile(r"^[A-Za-z0-9\-/ ]{3,24}$")


class ValueRejected(ValueError):
    """A value does not fit its question. Never raised to the owner; the agent re-asks."""


@dataclass(frozen=True)
class Question:
    id: str
    section: str
    section_title: dict
    type: str
    required: bool
    fills_by: str
    keys: tuple          # answer keys (instantiate) or (id,) for interview questions
    text: dict
    options: tuple       # ((value, labels), ...)
    default: Any
    default_note: dict = field(default_factory=dict)

    def option_values(self) -> list:
        return [v for v, _ in self.options]


@dataclass(frozen=True)
class Catalog:
    questions: tuple
    template: dict

    def get(self, qid: str) -> Optional[Question]:
        return next((q for q in self.questions if q.id == qid), None)

    def ids(self) -> list:
        return [q.id for q in self.questions]


def load_catalog(path: Any = None) -> Catalog:
    doc = json.loads(Path(path or DEFAULT_QUESTIONS).read_text(encoding="utf-8"))
    qs = []
    for s in doc["sections"]:
        for q in s["questions"]:
            keys = tuple(q.get("answerKeys") or (q["id"],))
            opts = tuple((o["value"], o["labels"]) for o in q.get("options", []))
            d = q["defaultIfUnknown"]
            qs.append(Question(q["id"], s["id"], s["title"], q["type"], bool(q["required"]), q["fillsBy"],
                               keys, q["text"], opts, d.get("value"), d.get("note", {})))
    if len({q.id for q in qs}) != len(qs):
        raise ValueError("duplicate question ids")
    return Catalog(tuple(qs), doc["template"])


def instantiate_module():
    """The template instantiator, loaded by path (it is a script, not a package)."""
    spec = importlib.util.spec_from_file_location("_dsc_instantiate", INSTANTIATE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _clean_text(v: Any, key: str) -> str:
    if not isinstance(v, str):
        raise ValueRejected(f"{key}: text required")
    v = v.strip()
    if not v or len(v) > MAX_TEXT or re.search(r"[{}]|[\x00-\x08\x0b-\x1f\x7f]", v):
        raise ValueRejected(f"{key}: empty, too long, or contains braces or control characters")
    return v


def validate_values(q: Question, values: Any) -> dict:
    """Return a clean {key: value} dict for the question or raise ValueRejected. Strict: keys must be
    exactly the question's answer keys; a model that returns anything else is rejected whole."""
    if not isinstance(values, dict) or set(values) != set(q.keys):
        raise ValueRejected("values must hold exactly the question's answer keys")
    out = {}
    for k, v in values.items():
        if q.type in ("text", "text_pair"):
            v = _clean_text(v, k)
            if q.id == "q_currency":
                v = v.upper()
                if not re.fullmatch(r"[A-Z]{3}", v):
                    raise ValueRejected("currency: three letters")
            elif q.id in ("q_cr_number", "q_vat_number") and not SIMPLE_CODE.match(v):
                raise ValueRejected(f"{k}: not a registration number")
        elif q.type == "boolean":
            if not isinstance(v, bool):
                raise ValueRejected(f"{k}: true or false required")
        elif q.type == "choice":
            if not isinstance(v, str) or v not in q.option_values():
                raise ValueRejected(f"{k}: not one of the options")
        elif q.type == "multi_choice":
            if (not isinstance(v, list) or not v or len(set(map(str, v))) != len(v)
                    or any(not isinstance(i, str) or i not in q.option_values() for i in v)):
                raise ValueRejected(f"{k}: a non-empty list of options without duplicates")
        elif q.type in ("integer", "number"):
            lo, hi = BOUNDS.get(q.id, DEFAULT_BOUNDS)
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
                raise ValueRejected(f"{k}: a finite number required")
            if q.type == "integer" and (isinstance(v, float) and not v.is_integer()):
                raise ValueRejected(f"{k}: a whole number required")
            v = int(v) if q.type == "integer" else v
            if not lo <= v <= hi:
                raise ValueRejected(f"{k}: outside {lo}..{hi}")
        else:
            raise ValueRejected(f"unsupported question type {q.type}")
        out[k] = v
    return out
