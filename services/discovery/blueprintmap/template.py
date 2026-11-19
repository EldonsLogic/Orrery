"""Loads the target vocabulary: the entities of the trading-distribution template (the only source
of Blueprint entity and field ids this library may use)."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from .errors import BlueprintMapError
from .table import FIELDS, MODELS

PARTS = Path(__file__).resolve().parents[1] / "templates" / "trading-distribution" / "parts"


def load_entities(parts: Path = PARTS) -> dict:
    """{entity_id: entity} from the template parts. Fails closed when unreadable."""
    out: dict = {}
    try:
        for f in sorted(parts.glob("entities-*.json")):
            for e in json.loads(f.read_text(encoding="utf-8")):
                out[e["id"]] = e
    except (OSError, ValueError, KeyError, TypeError):
        raise BlueprintMapError("BMP-E03") from None
    if not out:
        raise BlueprintMapError("BMP-E03")
    return out


def parse_target(t: str):
    """('field'|'rel'|'special'|'none', entity, name, inverted) for a table target."""
    inv = t.startswith("~")
    t = t.lstrip("~")
    if t.startswith("!"):
        return ("none", "", t[1:], False)
    if t.startswith("@"):
        k, _, n = t[1:].partition(".")
        return ("special", k, n, False)
    if "#" in t:
        e, _, n = t.partition("#")
        return ("rel", e, n, False)
    e, _, n = t.partition(".")
    return ("field", e, n, inv)


def check_table(entities: dict) -> list:
    """Table targets that do not resolve in the template (must be empty)."""
    bad = []
    for neutral, targets in sorted(FIELDS.items()):
        for t in targets:
            kind, e, n, _ = parse_target(t)
            ent = entities.get(e)
            if kind == "field" and not (ent and any(f["id"] == n for f in ent["fields"])):
                bad.append(f"{neutral} -> {t}")
            if kind == "rel" and not (ent and any(r["id"] == n for r in ent.get("relations", []))):
                bad.append(f"{neutral} -> {t}")
    for m, spec in sorted(MODELS.items()):
        if spec["kind"] == "entity":
            bad += [f"{m} -> {e}" for e in spec["args"] if e not in entities]
    return bad


def draft_entity(entities: dict, eid: str, fields: set, rels: set, models: list) -> dict:
    """Template entity trimmed to the mapped fields, with imported provenance."""
    t = entities[eid]
    e = {"id": eid, "labels": copy.deepcopy(t["labels"]), "kind": t.get("kind", "master"),
         "fields": [copy.deepcopy(f) for f in t["fields"] if f["id"] in fields],
         "provenance": {"source": "imported", "ref": ("odoo:" + ",".join(models))[:200], "humanEdited": False}}
    if "pluralLabels" in t:
        e["pluralLabels"] = copy.deepcopy(t["pluralLabels"])
    r = [copy.deepcopy(x) for x in t.get("relations", []) if x["id"] in rels]
    if r:
        e["relations"] = r
    return e
