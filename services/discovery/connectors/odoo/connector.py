"""Tier 1 (official API, read-only) Odoo extractor. Offline: all I/O goes through an injected
Transport behind a read-only gateway. Binary fields are never fetched."""
from __future__ import annotations

import json
from typing import Any, Iterable, Optional

from ..model import Budget, Registry
from . import mapping
from .errors import (ModelUnavailable, Odo003ModelNotAllowed, Odo006BadRequest, Odo007BadConfig,
                     Odo009MalformedResponse)
from .transport import MAX_PAGE_SIZE, ReadOnlyGateway, Transport, scan_secrets, secret_like

ISSUE_CAP = 200  # per code; the rest is counted in stats
META_ATTRS = ["type", "string", "required", "relation", "selection", "translate"]
REQUEST_KEYS = {"models", "lang"}


def _posint(name: str, v: Any, hi: Optional[int] = None) -> int:
    if isinstance(v, bool) or not isinstance(v, int) or v < 1 or (hi is not None and v > hi):
        raise Odo007BadConfig(f"{name} must be an integer 1..{hi if hi else 'n'}")
    return v


class OdooConnector:
    id = "discovery.odoo"
    version = "0.1.0"
    tier = 1
    writes = False
    capabilities = frozenset({"read"})

    def __init__(self, transport: Transport, models: Iterable = mapping.DEFAULT_MODELS, page_size: int = 100,
                 max_pages: int = 50, max_records_per_model: int = 5_000, max_records_total: int = 50_000):
        models = tuple(models)
        if not models or not all(isinstance(m, str) and m for m in models):
            raise Odo007BadConfig("models must be a non-empty list of model names")
        self.allowed_models = frozenset(models)
        self.default_models = tuple(dict.fromkeys(models))
        self.page_size = _posint("page_size", page_size, MAX_PAGE_SIZE)
        self.max_pages = _posint("max_pages", max_pages)
        self.max_records_per_model = _posint("max_records_per_model", max_records_per_model)
        self.max_records_total = _posint("max_records_total", max_records_total)
        self._gw = ReadOnlyGateway(transport, self.allowed_models)

    def __repr__(self) -> str:
        return f"OdooConnector(id={self.id}, models={len(self.allowed_models)})"

    # ---- extract -----------------------------------------------------------------------------
    def _request(self, source: bytes) -> dict:
        if not source.strip():
            req: Any = {}
        else:
            try:
                req = json.loads(source.decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                raise Odo006BadRequest("request is not UTF-8 JSON") from None
        if not isinstance(req, dict):
            raise Odo006BadRequest("request must be an object")
        scan_secrets(req, "request")  # credentials never travel as connector input
        extra = sorted(set(req) - REQUEST_KEYS)
        if extra:
            raise Odo006BadRequest(f"unknown request keys: {', '.join(extra)}")
        models = req.get("models", list(self.default_models))
        if not isinstance(models, list) or not all(isinstance(m, str) for m in models):
            raise Odo006BadRequest("models must be a list of names")
        for m in models:
            if m not in self.allowed_models:
                raise Odo003ModelNotAllowed("requested model is not on the allow-list")
        lang = req.get("lang")
        if lang is not None and (not isinstance(lang, str) or not lang.replace("_", "").isalnum()):
            raise Odo006BadRequest("lang must be a locale code such as ar_001")
        return {"models": list(dict.fromkeys(models)), "lang": lang}

    def extract(self, source: bytes, budget: Budget) -> list:
        req = self._request(source)
        ctx = {"context": {"lang": req["lang"]}} if req["lang"] else {}
        budget.tick()
        ver = self._gw.call("common", "version", [], {})
        if not isinstance(ver, dict):
            raise Odo009MalformedResponse("version must be an object")
        vinfo = {k: str(ver[k]) for k in ("server_version", "server_serie", "protocol_version")
                 if isinstance(ver.get(k), (str, int, float)) and not isinstance(ver.get(k), bool)}
        raw: list = [{"type": "server", "version": vinfo}]
        total = 0
        for model in req["models"]:
            budget.tick()
            item, n = self._model(model, ctx, budget, total)
            total += n
            raw.append(item)
        return raw

    def _model(self, model: str, ctx: dict, budget: Budget, total: int) -> tuple:
        gw = self._gw
        base = {"type": "model", "model": model, "unavailable": False, "fields": {}, "withheld": [],
                "binary": [], "records": [], "count": 0, "pages": 0, "truncated": ""}
        try:
            meta = gw.call(model, "fields_get", [], {"attributes": META_ATTRS, **ctx})
        except ModelUnavailable:
            return {**base, "unavailable": True}, 0
        if not isinstance(meta, dict):
            raise Odo009MalformedResponse("fields_get must return an object")
        fields: dict = {}
        fetch: list = []
        for name in sorted(meta):
            m = meta[name]
            if not isinstance(m, dict) or not isinstance(m.get("type"), str):
                raise Odo009MalformedResponse("field metadata malformed")
            budget.tick()
            if secret_like(name):
                base["withheld"].append(name)  # never fetched, never output
                continue
            sel = m.get("selection")
            fields[name] = {
                "type": m["type"], "string": m["string"] if isinstance(m.get("string"), str) else "",
                "required": m.get("required") is True,
                "relation": m["relation"] if isinstance(m.get("relation"), str) else "",
                "selection": [[str(p[0]), str(p[1])] for p in sel
                              if isinstance(p, (list, tuple)) and len(p) == 2] if isinstance(sel, list) else [],
                "translate": m.get("translate") is True}
            if m["type"] in mapping.BINARY_TYPES:
                base["binary"].append(name)  # refused: not fetched (flagged)
            else:
                fetch.append(name)
        base["fields"] = fields
        count = gw.call(model, "search_count", [[]], {})
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise Odo009MalformedResponse("search_count must return a count")
        base["count"] = count
        cap = min(self.max_records_per_model, max(0, self.max_records_total - total))
        records: list = []
        offset, pages = 0, 0
        known = set(fetch) | {"id"}
        while offset < count:
            if pages >= self.max_pages:
                base["truncated"] = "pages"
                break
            if len(records) >= cap:
                base["truncated"] = "records"
                break
            limit = min(self.page_size, cap - len(records))
            page = gw.call(model, "search_read", [[]],
                           {"fields": fetch, "limit": limit, "offset": offset, "order": "id", **ctx})
            if not isinstance(page, list) or not all(isinstance(r, dict) for r in page) or len(page) > limit:
                raise Odo009MalformedResponse("search_read must return at most `limit` objects")
            pages += 1
            budget.tick(len(page) + 1)
            for r in page:
                records.append({k: r[k] for k in sorted(r) if k in known})
            offset += len(page)
            if len(page) < limit:
                break
        base.update(records=records, pages=pages)
        return base, len(records)

    # ---- normalise ---------------------------------------------------------------------------
    def normalise(self, raw: list, budget: Budget) -> dict:
        entities, issues = [], []
        st = {k: 0 for k in ("models", "models_unavailable", "fields", "records", "cells", "empty_cells",
                             "pages", "binary_fields_skipped", "secret_like_withheld", "unmapped_fields",
                             "truncated_models", "issues_omitted")}
        seen: dict = {}

        def issue(sev: str, code: str, detail: str) -> None:
            seen[code] = seen.get(code, 0) + 1
            if seen[code] <= ISSUE_CAP:
                issues.append({"severity": sev, "code": code, "detail": detail})
            else:
                st["issues_omitted"] += 1

        for item in raw:
            budget.tick()
            if item["type"] == "server":
                fl = [{"path": f"server.{k}", "text": v, "kind": "metadata"} for k, v in sorted(item["version"].items())]
                entities.append({"name": "server", "kind": "metadata", "fields": fl})
                continue
            model = item["model"]
            st["models"] += 1
            if item["unavailable"]:
                st["models_unavailable"] += 1
                issue("info", "model_unavailable", f"{model}: not installed or not visible; skipped")
                continue
            out: list = []
            fmeta = item["fields"]
            known_model = model in mapping.MAPPING
            if not known_model:
                issue("warn", "unmapped_model", f"{model}: no export mapping; every field is unmapped")
            for name, m in fmeta.items():
                budget.tick()
                st["fields"] += 1
                nt = mapping.TYPE_MAP.get(m["type"], "unknown")
                hit = mapping.lookup(model, name)
                path = f"{model}.{name}"
                parts = [f"type={m['type']}", f"neutral_type={nt}"]
                if m["required"]:
                    parts.append("required=true")
                if m["relation"]:
                    parts.append(f"relation={m['relation']}")
                if m["selection"]:
                    parts.append("selection=" + "|".join(f"{k}:{v}" for k, v in m["selection"]))
                if m["translate"]:
                    parts.append("translate=true")
                out.append({"path": f"{path}#label", "text": m["string"], "kind": "column_header"})
                out.append({"path": f"{path}#spec", "text": "; ".join(parts), "kind": "metadata"})
                if hit:
                    out.append({"path": f"{path}#map", "text": f"{hit[0]}:{hit[1]}", "kind": "metadata"})
                else:
                    st["unmapped_fields"] += 1
                    issue("warn", "unmapped_field", f"{path} ({m['type']}); reported, not dropped")
            for name in item["binary"]:
                st["binary_fields_skipped"] += 1
                issue("warn", "binary_not_fetched", f"{model}.{name}: binary field refused by default")
            for name in item["withheld"]:
                st["secret_like_withheld"] += 1
                issue("warn", "secret_like_field_withheld", f"{model}.{name}: secret-like name; not fetched")
            if item["truncated"]:
                st["truncated_models"] += 1
                issue("warn", "budget_stopped_paging",
                      f"{model}: stopped by {item['truncated']} budget at {len(item['records'])} of {item['count']} records")
            st["pages"] += item["pages"]
            for idx, rec in enumerate(item["records"]):
                st["records"] += 1
                rid = rec.get("id") if isinstance(rec.get("id"), int) else f"n{idx}"
                for name in sorted(rec):
                    budget.tick()
                    cells = self._cells(fmeta.get(name, {}).get("type", "char"), rec[name])
                    if cells is None:
                        st["empty_cells"] += 1
                        continue
                    for suffix, text in cells:
                        st["cells"] += 1
                        out.append({"path": f"{model}[{rid}].{name}{suffix}", "text": text, "kind": "cell"})
            entities.append({"name": model, "kind": "table", "fields": out})
        return {"entities": entities, "issues": issues, "stats": st}

    @staticmethod
    def _cells(ftype: str, v: Any):
        """[(path_suffix, text)] or None when empty. False means empty for non-boolean fields."""
        if ftype == "boolean":
            return None if v is None else [("", "true" if v else "false")]
        if v is False or v is None or v == [] or v == "":
            return None
        if ftype == "many2one":
            if isinstance(v, (list, tuple)) and len(v) == 2:
                return [("", str(v[1])), ("#id", str(v[0]))]
            return [("#id", str(v))]
        if ftype in ("one2many", "many2many") and isinstance(v, list):
            return [("", ",".join(str(i) for i in v))]
        if ftype == "selection" and isinstance(v, (list, tuple)) and v:
            return [("", str(v[0]))]
        if isinstance(v, str):
            return [("", v)]
        if isinstance(v, (list, dict)):
            return [("", json.dumps(v, sort_keys=True, ensure_ascii=False))]
        return [("", str(v))]


def register(registry: Registry, transport: Transport, **kw: Any) -> OdooConnector:
    c = OdooConnector(transport, **kw)
    registry.register(c)
    return c
