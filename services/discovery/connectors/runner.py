"""Boundary runner: restricted call, sanitise, label, audit, fail closed (PI-002..PI-007)."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Callable, Optional

from .detect import instruction_hits
from .model import (DATA_CLASSES, Budget, BudgetExceeded, ConnectorRefusal, RunContext, check_connector)
from .sanitise import comparison_copy, script_flags, strip_controls

FIELD_KEYS = {"path", "text", "kind", "visible", "hidden_reason", "transform", "confidence"}
FIELD_KINDS = {"body", "header", "filename", "metadata", "ocr", "sender", "reply_to", "column_header",
               "cell", "comment", "title", "entity_name", "entity_kind", "issue", "other"}
TRANSFORMS = {"ocr", "parse", "normalise"}
SEVERITIES = {"info", "warn", "error"}
# Anything a connector sets that looks like a label is discarded and logged (PI-002).
LABEL_KEYS = {"trust", "trust_level", "level", "data_class", "class", "source", "content_hash",
              "sanitisation", "tenant_id", "content_id", "tainted", "parents", "envelope", "labels", "evidence"}
TRUNC_MARK = " [truncated]"


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _canon(v: Any) -> bytes:
    return json.dumps(v, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


class _Fail(Exception):
    def __init__(self, code: str, reason: str):
        super().__init__(reason)
        self.code, self.reason = code, reason


def _jsonlike(v: Any, depth: int, max_depth: int, budget: Budget) -> None:
    budget.tick()
    if depth > max_depth:
        raise _Fail("CON-011", "output nesting too deep")
    if v is None or isinstance(v, (str, bool, int, float)):
        return
    if isinstance(v, list):
        for x in v:
            _jsonlike(x, depth + 1, max_depth, budget)
    elif isinstance(v, dict):
        for k, x in v.items():
            if not isinstance(k, str):
                raise _Fail("CON-011", "non-string key in output")
            _jsonlike(x, depth + 1, max_depth, budget)
    else:
        raise _Fail("CON-011", f"non-JSON value of type {type(v).__name__} in output")


class _Run:
    def __init__(self, connector: Any, ctx: RunContext, sink: Optional[Callable[[dict], None]]):
        self.c, self.ctx, self.sink = connector, ctx, sink
        self.events: list = []
        self.n = 0
        self.totals = {"bidi": 0, "zero_width": 0, "unicode_tag": 0, "truncated": 0}
        self.flag_counts: dict = {}
        self.chars = 0

    def ev(self, type_: str, **kw: Any) -> None:
        self.events.append({"type": type_, "seq": len(self.events), "job_id": self.ctx.job_id,
                            "connector": getattr(self.c, "id", None), "tenant_id": self.ctx.tenant_id, **kw})

    def discard_labels(self, where: str, d: dict) -> dict:
        found = sorted(k for k in d if k in LABEL_KEYS)
        if found:
            self.ev("label.discarded", where=where, keys=found)
        return {k: v for k, v in d.items() if k not in LABEL_KEYS}

    def envelope(self, text: Any, kind: str, path: str, ref: str, visible: bool = True,
                 hidden_reason: str = "", transform: str = "parse", confidence: Any = None,
                 extra_flags: tuple = ()) -> dict:
        if not isinstance(text, str):
            raise _Fail("CON-011", f"field {path} text is not a string")
        lim = self.ctx.limits
        self.chars += len(text)
        if self.chars > lim.max_total_chars:
            raise BudgetExceeded("chars", lim.max_total_chars)
        original_hash = sha256(text.encode("utf-8", "surrogatepass"))
        clean, counts = strip_controls(text)
        flags = set(extra_flags)
        for k, flag in (("bidi", "bidi_control"), ("zero_width", "zero_width"), ("unicode_tag", "unicode_tag")):
            self.totals[k] += counts[k]
            if counts[k]:
                flags.add(flag)
        if len(clean) > lim.max_field_chars:
            clean = clean[:lim.max_field_chars] + TRUNC_MARK
            flags.add("truncated")
            self.totals["truncated"] += 1
        comp = comparison_copy(clean)
        flags.update(script_flags(clean, self.ctx.protected_names))
        if not visible:
            flags.add("hidden_text")
        hits = instruction_hits(comp)
        if hits:
            flags.add("instruction_like")
        self.n += 1
        cid = f"{self.ctx.job_id}/{self.n:05d}"
        facing = visible or self.ctx.include_hidden
        for f in flags:
            self.flag_counts[f] = self.flag_counts.get(f, 0) + 1
        if hits:
            self.ev("injection.suspected", content_id=cid, path=path, kind=kind,
                    patterns=[h[0] for h in hits], langs=sorted({h[1] for h in hits}))
        env = {
            "content_id": cid,
            "trust": "untrusted", "level": "L3",  # set here only (PI-002, PI-003)
            "tenant_id": self.ctx.tenant_id,
            "source": {"connector": self.c.id, "version": self.c.version, "tier": self.c.tier,
                       "job_id": self.ctx.job_id, "ref": ref, "path": path, "kind": kind},
            "data_class": self.ctx.data_class,
            "transform": transform,
            "sanitisation": {"stripped": dict(counts), "flags": sorted(flags)},
            "content_hash": sha256(clean.encode("utf-8", "surrogatepass")),
            "evidence_hash": original_hash,  # hash of the original bytes; original kept under source class
            "model_facing": facing,
            "text": clean if facing else None,
            "comparison": comp if facing else None,
        }
        if not visible:
            env["hidden_reason"] = self.envelope_text_safe(hidden_reason)
        if confidence is not None:
            env["confidence"] = confidence
        return env

    @staticmethod
    def envelope_text_safe(s: Any) -> str:
        clean, _ = strip_controls(s if isinstance(s, str) else "")
        return clean[:100]

    def field(self, d: Any, ref: str, prefix: str) -> dict:
        if not isinstance(d, dict):
            raise _Fail("CON-011", "field is not an object")
        d = self.discard_labels(f"{prefix}", d)
        unknown = sorted(set(d) - FIELD_KEYS)
        if unknown:
            raise _Fail("CON-011", f"unknown field keys: {', '.join(unknown)}")
        for req in ("path", "text", "kind"):
            if req not in d:
                raise _Fail("CON-011", f"field missing {req}")
        if not isinstance(d["path"], str) or d["kind"] not in FIELD_KINDS:
            raise _Fail("CON-011", "field has bad path or kind")
        vis = d.get("visible", True)
        if not isinstance(vis, bool):
            raise _Fail("CON-011", "visible must be boolean")
        tr = d.get("transform", "parse")
        if tr not in TRANSFORMS:
            raise _Fail("CON-011", "bad transform")
        conf = d.get("confidence")
        if conf is not None and (isinstance(conf, bool) or not isinstance(conf, (int, float)) or not 0 <= conf <= 1):
            raise _Fail("CON-011", "confidence must be a number in 0..1")
        return self.envelope(d["text"], d["kind"], d["path"], ref, vis, d.get("hidden_reason", ""), tr, conf)

    def addr_checks(self, fields: list) -> None:
        """PI-007: sender, reply-to and headers are L3; mismatches and look-alikes are flagged;
        no recipient is ever derived from them."""
        def dom(env: dict) -> str:
            t = (env["text"] or "").strip().rstrip(">").lower()
            return t.rsplit("@", 1)[-1] if "@" in t else ""
        sender = next((f for f in fields if f["source"]["kind"] == "sender"), None)
        for f in fields:
            if f["source"]["kind"] not in ("sender", "reply_to") or f["text"] is None:
                continue
            add = set()
            d = dom(f)
            for fl in script_flags(d, self.ctx.protected_names):
                add.add(fl)
            if d and any(skeleton_eq(d, p) for p in self.ctx.protected_names):
                add.add("confusable")
            if f["source"]["kind"] == "reply_to" and sender is not None and dom(sender) != d:
                add.add("reply_to_mismatch")
            if (f["source"]["kind"] == "sender" and self.c.tier == 4 and self.ctx.sender_allowlist
                    and (f["text"] or "").strip().lower() not in {a.lower() for a in self.ctx.sender_allowlist}):
                add.add("sender_not_allowlisted")
            for fl in add:
                if fl not in f["sanitisation"]["flags"]:
                    f["sanitisation"]["flags"] = sorted(set(f["sanitisation"]["flags"]) | {fl})
                    self.flag_counts[fl] = self.flag_counts.get(fl, 0) + 1


def skeleton_eq(domain: str, protected: str) -> bool:
    from .sanitise import skeleton
    return skeleton(domain) == protected.casefold() and domain.casefold() != protected.casefold()


def _refuse(r: _Run, code: str, reason: str, steps: int) -> dict:
    r.ev("connector.run", outcome="refused", code=code, steps=steps)
    r.ev("connector.alert", severity="alert", code=code)
    return _finish(r, {"ok": False, "code": code, "reason": reason})


def _finish(r: _Run, out: dict) -> dict:
    if r.sink is not None:
        try:
            for e in r.events:
                r.sink(dict(e))
        except Exception:
            return {"ok": False, "code": "CON-017", "reason": "audit sink failed; output withheld",
                    "events": r.events}
    out["events"] = r.events
    return out


def iter_envelopes(result: dict):
    """Yield every labelled item in a successful result."""
    for e in result.get("entities", []):
        yield e["name"]
        yield e["kind"]
        yield from e["fields"]
    for i in result.get("issues", []):
        yield i["code"]
        yield i["detail"]


def run_connector(connector: Any, source: Any, ctx: RunContext,
                  sink: Optional[Callable[[dict], None]] = None) -> dict:
    """Run one connector on bytes. Returns {"ok": True, ...labelled result...} or
    {"ok": False, "code": "CON-...", "reason": ...}. Never raises for connector faults, never
    returns partial output."""
    r = _Run(connector, ctx, sink)
    budget = Budget(ctx.limits.max_steps if isinstance(ctx, RunContext) else 0)
    try:
        if not isinstance(ctx, RunContext) or not ctx.tenant_id or not ctx.job_id or ctx.data_class not in DATA_CLASSES:
            raise _Fail("CON-012", "run context lacks tenant, job or valid data class")
        try:
            check_connector(connector)
        except ConnectorRefusal as e:
            raise _Fail(e.code, e.reason)
        if not isinstance(source, (bytes, bytearray)):
            raise _Fail("CON-016", "source must be bytes")
        lim = ctx.limits
        if len(source) > lim.max_input_bytes:
            raise BudgetExceeded("input_bytes", lim.max_input_bytes)
        data = bytes(source)
        src_hash = sha256(data)
        try:
            raw = connector.extract(data, budget)
        except BudgetExceeded:
            raise
        except Exception as e:  # fail closed on any connector fault
            raise _Fail("CON-010", f"extract raised {type(e).__name__}")
        if not isinstance(raw, list):
            raise _Fail("CON-011", "extract must return a list")
        if len(raw) > lim.max_items:
            raise BudgetExceeded("items", lim.max_items)
        _jsonlike(raw, 0, lim.max_depth, budget)
        raw_hash = sha256(_canon(raw))
        raw_copy = json.loads(_canon(raw).decode("utf-8"))  # isolated copy, no shared references
        try:
            norm = connector.normalise(raw_copy, budget)
        except BudgetExceeded:
            raise
        except Exception as e:
            raise _Fail("CON-010", f"normalise raised {type(e).__name__}")
        if not isinstance(norm, dict):
            raise _Fail("CON-011", "normalise must return an object")
        _jsonlike(norm, 0, lim.max_depth, budget)
        norm = r.discard_labels("normalise", norm)
        extra = sorted(set(norm) - {"entities", "issues", "stats"})
        if extra:
            raise _Fail("CON-011", f"unknown output keys: {', '.join(extra)}")
        ents = norm.get("entities", [])
        issues = norm.get("issues", [])
        stats = norm.get("stats", {})
        if not isinstance(ents, list) or not isinstance(issues, list) or not isinstance(stats, dict):
            raise _Fail("CON-011", "entities and issues must be lists, stats an object")
        if not all(isinstance(v, int) and not isinstance(v, bool) for v in stats.values()):
            raise _Fail("CON-011", "stats values must be integers")
        nfields = sum(len(e.get("fields", [])) if isinstance(e, dict) and isinstance(e.get("fields", []), list) else 0
                      for e in ents)
        if nfields > lim.max_fields:
            raise BudgetExceeded("fields", lim.max_fields)
        out_ents = []
        for ei, e in enumerate(ents):
            if not isinstance(e, dict):
                raise _Fail("CON-011", "entity is not an object")
            e = r.discard_labels(f"entity[{ei}]", e)
            if set(e) - {"name", "kind", "fields"} or "name" not in e or not isinstance(e.get("fields", []), list):
                raise _Fail("CON-011", "malformed entity")
            ref = f"entity[{ei}]"
            fields = []
            for f in e.get("fields", []):
                budget.tick()
                fields.append(r.field(f, ref, f"{ref}.field"))
            r.addr_checks(fields)
            out_ents.append({
                "name": r.envelope(e["name"], "entity_name", f"{ref}.name", ref),
                "kind": r.envelope(e.get("kind", ""), "entity_kind", f"{ref}.kind", ref),
                "fields": fields})
        out_issues = []
        for ii, i in enumerate(issues):
            if not isinstance(i, dict):
                raise _Fail("CON-011", "issue is not an object")
            i = r.discard_labels(f"issue[{ii}]", i)
            if set(i) - {"severity", "code", "detail"} or i.get("severity") not in SEVERITIES:
                raise _Fail("CON-011", "malformed issue")
            out_issues.append({
                "severity": i["severity"],
                "code": r.envelope(i.get("code", ""), "issue", f"issue[{ii}].code", f"issue[{ii}]"),
                "detail": r.envelope(i.get("detail", ""), "issue", f"issue[{ii}].detail", f"issue[{ii}]")})
    except BudgetExceeded as e:
        r.ev("budget_exceeded", kind=e.kind, limit=e.limit)
        return _refuse(r, "CON-013", f"{e.kind} budget exceeded", budget.used)
    except _Fail as e:
        return _refuse(r, e.code, e.reason, budget.used)
    except Exception as e:  # defensive: boundary code must also fail closed
        return _refuse(r, "CON-019", f"boundary error {type(e).__name__}", budget.used)

    r.ev("sanitisation.applied", counts=dict(r.totals), flags=dict(sorted(r.flag_counts.items())), items=r.n)
    r.ev("connector.run", outcome="ok", steps=budget.used, items=r.n, entities=len(out_ents),
         source_sha256=src_hash, source_bytes=len(data), raw_sha256=raw_hash)
    return _finish(r, {
        "ok": True, "tainted": True,
        "source": {"connector": connector.id, "version": connector.version, "tier": connector.tier,
                   "job_id": ctx.job_id, "trust": "untrusted", "level": "L3"},
        "entities": out_ents, "issues": out_issues, "stats": dict(stats),
        "evidence": {"source_sha256": src_hash, "source_bytes": len(data), "raw_sha256": raw_hash},
    })
