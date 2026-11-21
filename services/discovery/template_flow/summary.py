"""Owner-readable summary of a draft Blueprint (view model: data and i18n keys, no sentences)."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from . import pathing
from .errors import FlowError

HERE = Path(__file__).resolve().parent
DEFAULT_QUESTIONS = HERE.parents[0] / "templates" / "trading-distribution" / "questions.json"
SECTION_ORDER = ("company", "compliance", "locations", "roles", "approvals", "entities")
COUNTS = ("entities", "workflows", "roles", "approvals", "reports", "locations")


def load_registry(path: Path | None = None) -> list[dict]:
    reg = json.loads((path or HERE / "registry.json").read_text(encoding="utf-8"))["fields"]
    for f in reg:
        f["segs"] = tuple(f["pattern"][1:].split("/"))
    return reg


def load_questions(path: Path | None = None) -> list[dict]:
    q = json.loads((path or DEFAULT_QUESTIONS).read_text(encoding="utf-8"))
    return [{"id": x["id"], "section": s["id"], "text": x["text"]}
            for s in q["sections"] for x in s["questions"] if x.get("fillsBy") == "interview"]


def _subject(ancestors: list) -> dict | None:
    for a in reversed(ancestors):
        if isinstance(a, dict) and isinstance(a.get("labels"), dict) and isinstance(a.get("id"), str):
            return {"id": a["id"], "labels": copy.deepcopy(a["labels"])}
    return None


def _item(bp: dict, spec: dict, segs: tuple[str, ...]) -> dict:
    ancestors = []
    node: Any = bp
    for s in segs[:-1]:
        node = pathing.get(node, (s,))
        ancestors.append(node)
    value = copy.deepcopy(pathing.get(bp, segs))
    it = {"key": spec["key"], "labelKey": "tpl.field." + spec["key"], "pointer": "/" + "/".join(segs),
          "kind": spec["kind"], "value": value, "subject": _subject(ancestors), "editable": True,
          "untrustedText": spec["kind"] == "text"}
    if spec["kind"] == "enum":
        it["options"] = [{"value": v, "labelKey": "tpl.option." + v} for v in spec["values"]]
    if spec["kind"] in ("text", "digits"):
        it["constraints"] = {k: spec[k] for k in ("minLength", "maxLength", "length") if k in spec}
    if spec["kind"] == "number":
        it["constraints"] = {"min": spec["min"], "max": spec["max"]}
    return it


def build_summary(bp: dict, registry: list[dict], questions: list[dict], *, draft_hash: str) -> dict:
    sections: dict[str, list] = {s: [] for s in SECTION_ORDER}
    for spec in registry:
        for segs in pathing.expand(spec["segs"], bp):
            sections[spec["section"]].append(_item(bp, spec, segs))
        if spec.get("create"):  # optional field the draft does not have yet: offer it empty
            segs = spec["segs"]
            try:
                pathing.resolve(bp, segs, create_leaf=True)
            except FlowError:
                continue
            if not any(i["key"] == spec["key"] for i in sections[spec["section"]]):
                sections[spec["section"]].append({
                    "key": spec["key"], "labelKey": "tpl.field." + spec["key"], "pointer": "/" + "/".join(segs),
                    "kind": spec["kind"], "value": None, "subject": None, "editable": True, "untrustedText": False,
                    "constraints": {"length": spec["length"]}})
    meta = bp.get("meta", {})
    return {
        "schema": "template_flow.summary/1",
        "titleKey": "tpl.title",
        "noticeKey": "tpl.notice.draft",
        "final": False,
        "buildState": meta.get("buildState"),
        "revision": meta.get("revision"),
        "draftHash": draft_hash,
        "sections": [{"id": s, "labelKey": "tpl.section." + s, "items": sections[s]} for s in SECTION_ORDER if sections[s]],
        "counts": [{"key": c, "labelKey": "tpl.count." + c, "value": len(bp.get(c, []))} for c in COUNTS],
        "confirm": {"titleKey": "tpl.confirm.title", "questions": copy.deepcopy(questions)},
    }
