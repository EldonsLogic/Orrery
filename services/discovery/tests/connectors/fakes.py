"""Test-only fake connectors. Synthetic data, example.invalid domains. Not real connectors."""
import csv
import io
import json

from connectors import Budget


class Base:
    version = "0.0.1"
    writes = False
    capabilities = frozenset({"read", "parse"})

    def extract(self, source, budget):
        budget.tick()
        return [json.loads(source.decode("utf-8"))]


class PdfLike(Base):
    id = "test.pdf_like"
    tier = 3
    capabilities = frozenset({"read", "parse", "ocr"})

    def normalise(self, raw, budget):
        d = raw[0]
        fields = [{"path": "meta.title", "text": d.get("title", ""), "kind": "title"},
                  {"path": "meta.filename", "text": d.get("filename", ""), "kind": "filename"}]
        for i, s in enumerate(d.get("spans", [])):
            budget.tick()
            fields.append({"path": f"page1.span{i}", "text": s["text"], "kind": "ocr", "transform": "ocr",
                           "confidence": s.get("conf", 0.9), "visible": s.get("visible", True),
                           "hidden_reason": s.get("reason", "")})
        return {"entities": [{"name": d.get("filename", "doc"), "kind": "supplier_invoice", "fields": fields}]}


class EmailLike(Base):
    id = "test.email_like"
    tier = 4

    def normalise(self, raw, budget):
        d = raw[0]
        fields = [{"path": "header.from", "text": d["from"], "kind": "sender"},
                  {"path": "header.reply_to", "text": d["reply_to"], "kind": "reply_to"},
                  {"path": "header.subject", "text": d.get("subject", ""), "kind": "header"},
                  {"path": "body", "text": d["body"], "kind": "body"}]
        for k, v in d.get("headers", {}).items():
            fields.append({"path": f"header.{k}", "text": v, "kind": "header"})
        return {"entities": [{"name": "message", "kind": "email", "fields": fields}]}


class CsvLike(Base):
    id = "test.csv_like"
    tier = 2

    def extract(self, source, budget):
        rows = list(csv.reader(io.StringIO(source.decode("utf-8"))))
        for _ in rows:
            budget.tick()
        return [{"rows": rows}]

    def normalise(self, raw, budget):
        rows = raw[0]["rows"]
        head = rows[0] if rows else []
        fields = [{"path": f"col{i}", "text": h, "kind": "column_header"} for i, h in enumerate(head)]
        return {"entities": [{"name": "Sheet1", "kind": "table", "fields": fields}],
                "stats": {"rows": max(len(rows) - 1, 0)}}


def make(base, **over):
    """Subclass `base` with overridden attributes or methods."""
    return type("Fake", (base,), over)()
