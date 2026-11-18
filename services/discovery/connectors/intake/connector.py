"""The tier 3 (document OCR) intake connector: invoices, receipts and photos. Read-only.

Pipeline: file gate (headers only) -> injected OCR engine -> deterministic field rules -> framework
result. The runner wraps every field in an L3 envelope; nothing here adopts a stated number as truth.
"""
from __future__ import annotations

import re
from decimal import Decimal

from ..model import Budget, Registry
from .errors import Int009OcrFailed
from .fields import build_lines, extract_fields
from .gate import gate
from .ocr import OcrEngine, validate_result

ISSUE_CAP = 200
_SAFE = re.compile(r"[^A-Za-z0-9_.\-]")


def _num(x) -> str:
    return format(x, "g")


class IntakeConnector:
    id = "discovery.intake"
    version = "0.1.0"
    tier = 3
    writes = False
    capabilities = frozenset({"read", "parse", "ocr"})

    def __init__(self, engine: OcrEngine, confidence_threshold: float = 0.80, max_bytes: int = 10_000_000,
                 max_pages: int = 20, max_side: int = 8000, max_pixels: int = 40_000_000,
                 max_tokens: int = 20_000, languages: tuple = ("ar", "en"), tolerance: Decimal = Decimal("0")):
        if not callable(getattr(engine, "recognise", None)):
            raise TypeError("engine must provide recognise(image_bytes, hints)")
        self.engine, self.threshold = engine, confidence_threshold
        self.max_bytes, self.max_pages, self.max_side = max_bytes, max_pages, max_side
        self.max_pixels, self.max_tokens, self.languages, self.tolerance = max_pixels, max_tokens, languages, tolerance

    def extract(self, source: bytes, budget: Budget) -> list:
        budget.tick()
        info = gate(source, self.max_bytes, self.max_pages, self.max_side, self.max_pixels)
        raw = [{"type": "document", "kind": info["kind"], "pages": info["pages"], "width": info["width"],
                "height": info["height"], "bytes": len(source),
                "metadata": [{"key": _SAFE.sub("_", k)[:40] or "key", "text": v} for k, v in info["metadata"]]}]
        left = self.max_tokens
        for p in range(1, info["pages"] + 1):
            budget.tick()
            hints = {"page": p, "kind": info["kind"], "languages": list(self.languages)}
            try:
                res = self.engine.recognise(source, hints)
            except Exception as e:
                raise Int009OcrFailed(f"engine raised {type(e).__name__}")
            res = validate_result(res, left)
            left -= len(res.tokens)
            budget.tick(len(res.tokens))
            raw.append({"type": "page", "page": p, "language": res.language,
                        "tokens": [{"t": t.text, "c": t.confidence, "b": [t.box[i] for i in range(4)], "l": t.line,
                                    "v": t.visible, "r": t.hidden_reason if isinstance(t.hidden_reason, str) else "",
                                    "g": t.language if isinstance(t.language, str) else ""} for t in res.tokens]})
        return raw

    def normalise(self, raw: list, budget: Budget) -> dict:
        issues, ents = [], []
        st = {k: 0 for k in ("pages", "tokens", "lines", "hidden_tokens", "low_confidence_tokens", "values",
                             "needs_human_check", "line_items", "mismatch", "metadata_fields", "issues_omitted")}
        counts: dict = {}

        def issue(sev, code, detail):
            if counts.get(code, 0) < ISSUE_CAP:
                issues.append({"severity": sev, "code": code, "detail": detail})
            else:
                st["issues_omitted"] += 1
            counts[code] = counts.get(code, 0) + 1

        doc = raw[0]
        # Locator is structural (index), never the file's own key text: keys can be arbitrary and the runner
        # only accepts a strict ASCII locator (DSC-010 review F1).
        meta = [{"path": f"meta:{i}", "text": f"{m['key']}: {m['text']}", "kind": "metadata"}
                for i, m in enumerate(doc["metadata"], start=1)]
        st["metadata_fields"] = len(meta)
        if meta:
            ents.append({"name": "document_metadata", "kind": "metadata", "fields": meta})
            issue("info", "metadata_untrusted", "file metadata kept as untrusted text; never used as a value")
        text_fields, hidden_fields, all_lines = [], [], []
        for page in raw[1:]:
            budget.tick()
            st["pages"] += 1
            hid: dict = {}
            for t in page["tokens"]:
                budget.tick()
                st["tokens"] += 1
                if not t["v"]:
                    st["hidden_tokens"] += 1
                    hid.setdefault(t["l"], []).append(t)
                elif t["c"] < self.threshold:
                    st["low_confidence_tokens"] += 1
            for ln in sorted(hid):
                toks = hid[ln]
                hidden_fields.append({"path": f"page{page['page']}/hidden/{ln}", "kind": "ocr", "transform": "ocr",
                                      "text": " ".join(t["t"] for t in toks), "visible": False,
                                      "hidden_reason": toks[0]["r"] or "hidden_text"})
            for line in build_lines(page):
                st["lines"] += 1
                all_lines.append(line)
                text_fields.append({"path": f"page{line['page']}/line{line['line']}", "text": line["raw"],
                                    "kind": "ocr", "transform": "ocr",
                                    "confidence": min(t["c"] for t in line["tokens"])})
        if st["hidden_tokens"]:
            issue("warn", "hidden_text", f"{st['hidden_tokens']} hidden or invisible tokens excluded from "
                                         "extraction and from the model-facing copy")
        if st["low_confidence_tokens"]:
            issue("info", "low_confidence", f"{st['low_confidence_tokens']} tokens below {self.threshold}")
        if text_fields:
            ents.append({"name": "ocr_text", "kind": "ocr_text", "fields": text_fields})
        if hidden_fields:
            ents.append({"name": "hidden_text", "kind": "ocr_text", "fields": hidden_fields})
        res = extract_fields(all_lines, self.threshold, self.tolerance)
        st["line_items"] = res["stats"]["line_items"]
        vf = []
        for v in res["values"]:
            budget.tick()
            st["values"] += 1
            fl = list(v["flags"])
            nhc = bool(fl)
            if nhc:
                st["needs_human_check"] += 1
                issue("warn", "needs_human_check", f"field:{v['name']} ({', '.join(fl)})")
            base = f"field:{v['name']}"
            vf.append({"path": base, "text": v["text"], "kind": "other", "transform": "parse",
                       "confidence": v["conf"]})
            vf.append({"path": base + "#meta", "kind": "other", "transform": "parse",
                       "text": f"UNVERIFIED; page={v['page']}; line={v['line']}; "
                               f"box={','.join(_num(x) for x in v['box'])}; confidence={_num(v['conf'])}; "
                               f"needs_human_check={'true' if nhc else 'false'}; flags={','.join(fl)}"})
            if v["norm"] is not None:
                vf.append({"path": base + "#norm", "text": v["norm"], "kind": "other", "transform": "normalise"})
        if vf:
            ents.append({"name": "extracted_fields", "kind": "invoice", "fields": vf})
        cf = []
        for c in res["checks"]:
            cf.append({"path": f"check:{c['name']}", "kind": "other", "transform": "normalise",
                       "text": f"{c['status']}; {c['detail']}; computed in code; stated values are not adopted "
                               "or corrected"})
            if c["status"] == "mismatch":
                st["mismatch"] += 1
                issue("warn", "mismatch", f"{c['name']}: {c['detail']}")
        if cf:
            ents.append({"name": "checks", "kind": "checks", "fields": cf})
        return {"entities": ents, "issues": issues, "stats": st}


def register(registry: Registry, engine: OcrEngine) -> IntakeConnector:
    c = IntakeConnector(engine)
    registry.register(c)
    return c
