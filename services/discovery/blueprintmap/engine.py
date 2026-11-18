"""DSC-013 engine: neutral Odoo intermediate records -> mapping report + draft Blueprint fragment.
Pure, offline, stdlib only, deterministic. All source text is untrusted data: it is only compared,
counted or copied (cleaned and capped) into labels; it never selects a target, is never evaluated.
Ledger, tax, stock and payroll meaning is not interpreted (ADR-0027): such fields are reported
unmapped and `needs_human`; accounts and taxes are only listed as reference data."""
from __future__ import annotations

import re
import unicodedata
from typing import Any

from connectors.odoo import mapping as odoo

from . import table
from .errors import HUMAN_REASONS, REASON_KEYS, BlueprintMapError
from .template import check_table, draft_entity, load_entities, parse_target

MAX_MODELS, MAX_FIELDS, MAX_RECORDS, MAX_BUCKET = 200, 2000, 50_000, 200
NAME = re.compile(r"^[a-z][a-z0-9_]{0,62}(\.[a-z0-9_]{1,63}){0,3}$")
ID = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
BIDI = dict.fromkeys(map(ord, "​‎‏؜‪‫‬‭‮⁦⁧⁨⁩﻿"))
LOCATION_ID_PREFIX = "wh_"


def clean(v: Any, n: int = 120) -> str:
    """Untrusted text made safe to carry: NFC, control and bidi-override characters removed, capped."""
    s = unicodedata.normalize("NFC", v if isinstance(v, str) else "").translate(BIDI)
    return "".join(c for c in s if unicodedata.category(c) != "Cc").strip()[:n]


def _entry(**kw) -> dict:
    r = kw.get("reason")
    if r:
        kw["reason_key"] = REASON_KEYS[r]
    return kw


class _Run:
    def __init__(self, entities: dict):
        self.ent = entities
        self.rep = {k: [] for k in ("mapped", "unmapped_field", "unmapped_model", "needs_human", "conflicts")}
        self.taken: dict = {}      # (entity, field_id) -> (model, field)
        self.fields: dict = {}     # entity -> set of field ids
        self.rels: dict = {}       # entity -> set of relation ids
        self.srcs: dict = {}       # entity -> source models
        self.special: dict = {}    # (kind, name) -> [(model, source field)]
        self.stats = {"models": 0, "fields": 0, "records": 0}
        self.human_seen: set = set()

    def human(self, model: str, code: str, field: str = "", count: int = 0) -> None:
        key = (model, field, code)
        if key not in self.human_seen:
            self.human_seen.add(key)
            e = _entry(model=model, code=code, reason=code)
            e["reason_key"] = REASON_KEYS[code]
            e["field"], e["count"] = field, count
            self.rep["needs_human"].append(e)

    def unmapped(self, model: str, field: str, reason: str, neutral: str = "") -> None:
        self.rep["unmapped_field"].append(_entry(model=model, field=field, neutral=neutral, reason=reason))
        if reason in HUMAN_REASONS:
            self.human(model, reason, field)

    def conflict(self, model: str, field: str, target: str, reason: str, other: str = "") -> None:
        self.rep["conflicts"].append(_entry(model=model, field=field, target=target, reason=reason, other=other))

    def map_field(self, model: str, name: str, meta: dict, spec: dict) -> None:
        self.stats["fields"] += 1
        if not NAME.match(name) or not isinstance(meta, dict):
            return self.unmapped(model, clean(name, 64), "invalid_name")
        ntype = odoo.TYPE_MAP.get(meta.get("type"), "unknown")
        hit = odoo.lookup(model, name)
        if hit is None:
            return self.unmapped(model, name, "binary_not_fetched" if ntype == "binary" else "no_neutral_name")
        neutral = hit[0]
        targets = [parse_target(t) for t in table.FIELDS.get(neutral, ())]
        if not targets:
            return self.unmapped(model, name, "no_blueprint_home", neutral)
        wanted = [t for t in targets if t[0] == "none" or (t[0] == "special" and self._special_ok(spec, t))
                  or (t[0] in ("field", "rel") and t[1] in spec["args"])]
        if not wanted:
            return self.unmapped(model, name, "no_blueprint_home", neutral)
        for kind, e, n, inv in wanted:
            if kind == "none":
                self.unmapped(model, name, n, neutral)
            elif kind == "special":
                self.special.setdefault((e, n), []).append((model, name))
                self.rep["mapped"].append(_entry(model=model, field=name, neutral=neutral, target=f"@{e}.{n}".rstrip(".")))
            else:
                self._place(model, name, neutral, ntype, kind, e, n, inv)

    def _special_ok(self, spec: dict, t: tuple) -> bool:
        return (spec["kind"], t[1]) in {("location", "location"), ("company", "company"), ("reference", "ref"),
                                        ("entity", "routing"), ("reference", "routing")}

    def _place(self, model, name, neutral, ntype, kind, e, n, inv) -> bool:
        tgt = f"{e}.{n}" if kind == "field" else f"{e}#{n}"
        if kind == "rel":
            ok = ntype in ("reference_list", "reference")
        else:
            fdef = next(f for f in self.ent[e]["fields"] if f["id"] == n)
            ok = fdef["type"] in table.COMPAT.get(ntype, set())
        if not ok:
            self.conflict(model, name, tgt, "type_mismatch")
            return False
        prev = self.taken.get((e, tgt))
        if prev and prev != (model, name):
            self.conflict(model, name, tgt, "target_taken", f"{prev[0]}.{prev[1]}")
            return False
        self.taken[(e, tgt)] = (model, name)
        (self.fields if kind == "field" else self.rels).setdefault(e, set()).add(n)
        if model not in self.srcs.setdefault(e, []):
            self.srcs[e].append(model)
        m = _entry(model=model, field=name, neutral=neutral, target=tgt)
        if inv:
            m["inverted"] = True
        if kind == "field":
            fdef = next(f for f in self.ent[e]["fields"] if f["id"] == n)
            if "computed" in fdef:
                m["target_computed"] = True
            if fdef["type"] in table.ENUM_REVIEW_TARGETS:
                self.human(model, "enum_values_review", name)
        self.rep["mapped"].append(m)
        return True


def _records(item: dict, run: _Run) -> list:
    recs = item.get("records") if isinstance(item.get("records"), list) else []
    recs = [r for r in recs if isinstance(r, dict)]
    run.stats["records"] += len(recs)
    if run.stats["records"] > MAX_RECORDS:
        raise BlueprintMapError("BMP-E02", "records")
    return recs


def _ref_label(rec: dict, fields: list) -> str:
    return " ".join(x for x in (clean(rec.get(f)) for f in fields) if x)


def _build_locations(run: _Run, recs_by_model: dict, spec_by_model: dict) -> list:
    out, seen = [], set()
    lab = run.special.get(("location", "labels"), [])
    idf = {m: f for m, f in run.special.get(("location", "id"), [])}
    for model, field in lab:
        for rec in recs_by_model.get(model, ()):
            name = clean(rec.get(field))
            sid = rec.get("id") if isinstance(rec.get("id"), int) else None
            slug = re.sub(r"[^a-z0-9_]", "_", clean(rec.get(idf.get(model, ""))).lower())
            lid = slug if ID.match(slug) else (f"{LOCATION_ID_PREFIX}{sid}" if sid is not None else "")
            if not name or not ID.match(lid):
                run.human(model, "invalid_value", field)
                continue
            if lid in seen:
                run.conflict(model, field, "locations.id", "duplicate_id")
                continue
            if len(out) >= MAX_BUCKET:
                break
            seen.add(lid)
            out.append({"id": lid, "kind": spec_by_model[model]["args"][0], "labels": {"ar": name, "en": name}})
            run.human(model, "label_locale_unverified", field)
    return sorted(out, key=lambda x: x["id"])


def _build_company(run: _Run, recs_by_model: dict) -> dict:
    co: dict = {}
    for (kind, key), srcs in sorted(run.special.items()):
        if kind != "company":
            continue
        model, field = srcs[0]
        recs = recs_by_model.get(model, ())
        raw = recs[0].get(field) if recs else None
        if key == "currency" and isinstance(raw, (list, tuple)) and len(raw) == 2:
            raw = raw[1]
        v = clean(raw, 200)
        if not v:
            continue
        if key == "legalName":
            co[key] = {"ar": v, "en": v}
            run.human(model, "label_locale_unverified", field)
        elif key == "vatNumber" and re.fullmatch(r"[0-9]{15}", v):
            co[key] = v
        elif key == "currency" and re.fullmatch(r"[A-Z]{3}", v):
            co["locale"] = {"currency": v}
        else:
            run.human(model, "invalid_value", field)
    return co


def _build_reference(run: _Run, recs_by_model: dict) -> dict:
    out: dict = {}
    for (kind, bucket), srcs in sorted(run.special.items()):
        if kind != "ref":
            continue
        for model in sorted({m for m, _ in srcs}):
            fields = [f for m, f in srcs if m == model]
            for rec in recs_by_model.get(model, ()):
                label = _ref_label(rec, fields)
                if label and len(out.setdefault(bucket, [])) < MAX_BUCKET:
                    out[bucket].append({"model": model, "source_id": rec.get("id") if isinstance(rec.get("id"), int) else None,
                                        "label": label})
    return out


def map_records(data: Any, entities: dict | None = None) -> dict:
    """data: the Odoo connector's raw extract (a list) or {"models": [...]}.
    Returns {"report": {...}, "fragment": {...}}."""
    items = data.get("models") if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise BlueprintMapError("BMP-E01", "models")
    items = [i for i in items if isinstance(i, dict) and i.get("type", "model") == "model"]
    if len(items) > MAX_MODELS:
        raise BlueprintMapError("BMP-E02", "models")
    ent = entities if entities is not None else load_entities()
    if check_table(ent):
        raise BlueprintMapError("BMP-E04")
    run = _Run(ent)
    order = list(table.MODELS)
    items.sort(key=lambda i: (order.index(i["model"]) if i.get("model") in table.MODELS else len(order), str(i.get("model"))))
    recs_by_model: dict = {}
    spec_by_model: dict = {}
    for it in items:
        model = it.get("model")
        run.stats["models"] += 1
        if not isinstance(model, str) or not NAME.match(model):
            run.rep["unmapped_model"].append(_entry(model=clean(model, 64), reason="invalid_name", field_count=0))
            continue
        fmeta = it.get("fields") if isinstance(it.get("fields"), dict) else {}
        if len(fmeta) > MAX_FIELDS:
            raise BlueprintMapError("BMP-E02", "fields")
        spec = table.MODELS.get(model)
        recs = _records(it, run)
        if it.get("unavailable") is True:
            run.rep["unmapped_model"].append(_entry(model=model, reason="model_unavailable", field_count=0))
            continue
        if spec is None or spec["kind"] == "unmapped":
            reason = spec["args"][0] if spec else ("no_blueprint_entity" if model in odoo.MAPPING else "no_neutral_name")
            run.rep["unmapped_model"].append(_entry(model=model, reason=reason, field_count=len(fmeta)))
            if spec and spec["human"]:
                run.human(model, spec["human"], count=len(recs))
            continue
        recs_by_model[model], spec_by_model[model] = recs, spec
        if spec["human"]:
            run.human(model, spec["human"], count=len(recs))
        for name in sorted(fmeta, key=lambda f: (table.FIELD_ORDER.get((odoo.lookup(model, f) or ("",))[0], 10**6), str(f))):
            run.map_field(model, name, fmeta[name], spec)
        for m, f, vals, code in table.RECORD_CHECKS:
            if m == model:
                n = sum(1 for r in recs if isinstance(r.get(f), str) and r[f] in vals)
                if n:
                    run.human(model, code, f, n)
    frag_entities = [draft_entity(ent, e, run.fields[e], run.rels.get(e, set()), run.srcs[e])
                     for e in sorted(run.fields)]
    fragment = {"entities": frag_entities, "locations": _build_locations(run, recs_by_model, spec_by_model),
                "company": _build_company(run, recs_by_model), "reference_data": _build_reference(run, recs_by_model)}
    for k in run.rep:
        run.rep[k].sort(key=lambda x: (x["model"], x.get("field", ""), x.get("target", ""), x.get("reason", x.get("code", ""))))
    run.rep["stats"] = {**run.stats, **{k: len(v) for k, v in run.rep.items()}}
    return {"report": run.rep, "fragment": fragment}
