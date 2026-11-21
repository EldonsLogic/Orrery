"""Deterministic gap analysis of a Blueprint draft against the component library (DSC-006).

No model calls, no clock, no randomness, no I/O besides reading labels.json. Fails closed: a requirement is
`covered` only when a validly admitted, eligible manifest provides a matching artifact (or, for a component
binding or the e-invoicing component, the named component) in a version the Blueprint accepts, its own
`requires` are met and the Blueprint's parameter values and engine target fit it. Anything doubtful is
`partial` (a configuration gap) or `uncovered` (a candidate component request for BPL-016).
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

_BP = str(Path(__file__).resolve().parents[2] / "blueprint")
if _BP not in sys.path:
    sys.path.insert(0, _BP)

from registry import Registry  # noqa: E402
from validator import semver  # noqa: E402

SCHEMA_VERSION = "1"
KIND_ORDER = {"compliance": 0, "component": 1, "entity": 2, "workflow": 3, "report": 4}
STATUSES = ("covered", "partial", "uncovered")
MAX_ID = 200
_LABELS = json.loads((Path(__file__).with_name("labels.json")).read_text(encoding="utf-8"))
_NUMERIC = {"integer", "decimal", "percent", "money"}


def render(key: str, params: dict | None = None, locale: str = "en") -> str:
    """Label for an i18n key. Unknown key or locale: the key itself (never raises)."""
    text = _LABELS.get(locale, {}).get(key)
    if text is None:
        return key
    for k, v in (params or {}).items():
        text = text.replace("{" + k + "}", str(v))
    return text


def _lab(key: str, params: dict | None = None) -> dict:
    return {"ar": render(key, params, "ar"), "en": render(key, params, "en")}


def _s(v: Any) -> str | None:
    return v if isinstance(v, str) and 0 < len(v) <= MAX_ID else None


def _reason(code: str, **params: Any) -> dict:
    p = {k: v for k, v in params.items() if v is not None}
    return {"code": code, "key": f"gap.reason.{code}", "params": p, "labels": _lab(f"gap.reason.{code}", p)}


def _vkey(v: str):
    a, b, c, pre = semver.parse_version(v)
    return (a, b, c, pre == (), pre)


def _satisfies(version: str, rng: str) -> bool | None:
    """True/False, or None when the range is invalid."""
    try:
        return bool(semver.satisfies(version, rng))
    except (ValueError, TypeError):
        return None


class _Lib:
    """Read-only view: admitted manifests, eligibility, and what rejected entries claim."""

    def __init__(self, library: Any, environment: str):
        raws: list = []
        if isinstance(library, Registry):
            self.reg = library
        else:
            raws = list(library) if isinstance(library, (list, tuple)) else []
            try:
                self.reg = Registry.from_manifests(raws)
            except Exception:  # fail closed: nothing admitted
                self.reg = Registry.from_manifests([])
        self.environment = environment
        self.eligible = set(self.reg.eligible(environment))
        self.rejected = 0
        self.claims: dict[tuple, list[str]] = {}  # (type, ref) -> subjects of rejected entries claiming it
        for i, m in enumerate(raws):
            ok = False
            if isinstance(m, dict) and _s(m.get("id")) and _s(m.get("version")):
                try:
                    ok = self.reg.get(m["id"], m["version"]) == m
                except Exception:
                    ok = False
            if ok:
                continue
            self.rejected += 1
            subj = f"entry[{i}]"
            for t, r in self._claimed(m):
                self.claims.setdefault((t, r), []).append(subj)

    @staticmethod
    def _claimed(m: Any):
        if not isinstance(m, dict):
            return
        cid = _s(m.get("id"))
        if cid:
            yield ("component", cid)
        prov = m.get("provides")
        for p in prov if isinstance(prov, list) else []:
            arts = p.get("artifacts") if isinstance(p, dict) else None
            for a in arts if isinstance(arts, list) else []:
                if isinstance(a, dict) and _s(a.get("type")) and _s(a.get("ref")):
                    yield (a["type"], a["ref"])

    def manifests(self, cid: str):
        for v in self.reg.versions(cid):
            yield self.reg.get(cid, v)

    def artifact_candidates(self, atype: str, ref: str) -> list[tuple]:
        out = []
        for cid in self.reg.list_components():
            for m in self.manifests(cid):
                for p in m["provides"]:
                    if any(a["type"] == atype and a["ref"] == ref for a in p["artifacts"]):
                        out.append((cid, m["version"], p["capability"]))
                        break
        return out

    def component_candidates(self, cid: str, need_prefix: str | None = None) -> list[tuple]:
        out = []
        for m in self.manifests(cid):
            caps = [p["capability"] for p in m["provides"] if not need_prefix or p["capability"].startswith(need_prefix)]
            out.append((cid, m["version"], caps[0] if caps else None))
        return out

    def requirement_unmet(self, m: dict) -> str | None:
        for r in m["requires"]:
            rng = r["versionRange"]
            if "component" in r:
                vs = self.reg.versions(r["component"])
                ok = any(_satisfies(v, rng) for v in vs)
                if not ok:
                    return r["component"]
            else:
                ok = False
                for cid, v in self.reg.provides(r["capability"]):
                    if _satisfies(v, rng):
                        ok = True
                        break
                if not ok:
                    return r["capability"]
        return None


def _param_issues(m: dict, params: Any) -> list[tuple]:
    """(code, parameter id) for each problem between a binding's parameters and the manifest's declarations."""
    out = []
    given = params if isinstance(params, dict) else {}
    decl = {p["id"]: p for p in m["parameters"]}
    for k in sorted(given, key=str):
        p = decl.get(k)
        if p is None:
            out.append(("parameter_unknown", str(k)[:64]))
            continue
        v, t = given[k], p["type"]
        bad = False
        if t == "boolean":
            bad = not isinstance(v, bool)
        elif t == "integer":
            bad = not isinstance(v, int) or isinstance(v, bool)
        elif t in _NUMERIC:
            bad = not isinstance(v, (int, float, str)) or isinstance(v, bool)
            if not bad:
                try:
                    float(v)
                except ValueError:
                    bad = True
        elif t == "enum":
            bad = v not in p.get("enumValues", [])
        else:
            bad = not isinstance(v, str)
        if not bad and t in _NUMERIC:
            try:
                f = float(v)
                if f != f or ("min" in p and f < p["min"]) or ("max" in p and f > p["max"]):
                    bad = True
            except (ValueError, OverflowError):
                bad = True
        if bad:
            out.append(("parameter_invalid", k))
    for pid in sorted(decl):
        if decl[pid].get("required") and "default" not in decl[pid] and pid not in given:
            out.append(("parameter_missing", pid))
    return out


class _Ctx:
    def __init__(self, bp: dict, lib: _Lib):
        self.lib = lib
        self.bindings: dict[str, list[dict]] = {}
        self.malformed = 0
        comps = bp.get("components")
        for c in comps if isinstance(comps, list) else []:
            if isinstance(c, dict) and _s(c.get("id")) and isinstance(c.get("versionRange"), str):
                self.bindings.setdefault(c["id"], []).append(c)
            else:
                self.malformed += 1
        meta = bp.get("meta") if isinstance(bp.get("meta"), dict) else {}
        et = meta.get("engineTarget")
        self.target = et if isinstance(et, dict) and et else None

    def decide(self, ref: str, candidates: list[tuple], claim_keys: list[tuple], missing: dict | None = None,
               prefer: frozenset = frozenset()) -> dict:
        """Status, reasons, chosen provider and alternatives for one requirement."""
        reasons: list[dict] = []
        usable: list[tuple] = []  # (cid, version, capability, manifest)
        if not candidates:
            reasons.append(missing or _reason("no_provider", ref=ref))
        for cid, ver, cap in candidates:
            m = self.lib.reg.get(cid, ver)
            if m is None:
                continue
            if cap is None:
                reasons.append(_reason("capability_mismatch", component=cid))
                continue
            if (cid, ver) not in self.lib.eligible:
                reasons.append(_reason("not_eligible", component=cid, version=ver, environment=self.lib.environment))
                continue
            rejected_range = False
            for b in self.bindings.get(cid, []):
                s = _satisfies(ver, b["versionRange"])
                if s is None:
                    reasons.append(_reason("range_invalid", component=cid, range=str(b["versionRange"])[:64]))
                    rejected_range = True
                elif not s:
                    reasons.append(_reason("version_unsatisfied", component=cid, range=b["versionRange"][:64]))
                    rejected_range = True
            if rejected_range:
                continue
            unmet = self.lib.requirement_unmet(m)
            if unmet:
                reasons.append(_reason("requires_unmet", component=cid, requirement=unmet))
                continue
            usable.append((cid, ver, cap, m))
        if not usable:
            if any(k in self.lib.claims for k in claim_keys):
                reasons.append(_reason("rejected_entry", ref=ref))
            return {"status": "uncovered", "reasons": _dedupe(reasons), "match": None, "alternatives": []}
        # deterministic pick: a component the item names as its implementation, then one the Blueprint binds, then component id, then highest version
        # deterministic pick: a component the item names as its implementation, then one the Blueprint binds, then component id; highest version per component
        best_by_comp: dict[str, tuple] = {}
        for u in sorted(usable, key=lambda u: (u[0], _vkey(u[1])), reverse=False):
            best_by_comp[u[0]] = u  # highest version per component wins (sorted ascending)
        ordered = sorted(best_by_comp.values(), key=lambda u: (u[0] not in prefer, u[0] not in self.bindings, u[0]))
        cid, ver, cap, m = ordered[0]
        alts = [u[0] for u in ordered[1:]]
        status = "covered"
        reasons = []
        if alts:
            reasons.append(_reason("duplicate_providers", component=cid))
        gaps = []
        for b in self.bindings.get(cid, [])[:1]:
            gaps += _param_issues(m, b.get("parameters"))
        for code, pid in gaps:
            reasons.append(_reason(code, component=cid, parameter=pid))
        if self.target is not None:
            ec = m["engineCompatibility"]
            vs = self.target.get("versionSet")
            if ec["adapter"] != self.target.get("adapter") or (isinstance(vs, str) and vs not in ec.get("testedAgainst", [])):
                reasons.append(_reason("engine_incompatible", component=cid))
                gaps.append(("engine_incompatible", cid))
        if gaps:
            status = "partial"
        reasons.insert(0, _reason("matched", component=cid, version=ver, capability=cap))
        match = {"component": cid, "version": ver, "capability": cap,
                 "certification": m["certification"]["level"], "production_eligible": (cid, ver) in set(self.lib.reg.eligible("production"))}
        return {"status": status, "reasons": reasons, "match": match, "alternatives": alts}


def _dedupe(rs: list[dict]) -> list[dict]:
    seen, out = set(), []
    for r in rs:
        k = json.dumps([r["code"], r["params"]], sort_keys=True)
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out


def _labels(item: dict) -> dict:
    lab = item.get("labels")
    return {k: lab[k] for k in ("ar", "en") if isinstance(lab, dict) and isinstance(lab.get(k), str)}


def _evidence(pointer: str, item: dict, match: dict | None) -> list[dict]:
    ev = [{"kind": "blueprint", "id": pointer}]
    prov = item.get("provenance")
    if isinstance(prov, dict) and isinstance(prov.get("source"), str):
        ref = prov.get("ref")
        ev.append({"kind": "provenance", "id": prov["source"] + (":" + ref if isinstance(ref, str) else "")})
    if match:
        ev.append({"kind": "manifest", "id": f"{match['component']}@{match['version']}", "capability": match["capability"]})
    return ev


def analyse(blueprint: Any, library: Any, environment: str = "sandbox") -> dict:
    """Compare a Blueprint draft with the library.

    `library` is a `registry.Registry` or a list of raw manifest dicts (admitted through the registry; anything
    that fails admission provides nothing and is counted in `summary.library_entries_rejected`).
    `environment` is "sandbox" or "production" (any other value makes every component ineligible).
    Returns a JSON-safe dict; same input, same output, byte for byte.
    """
    bp = blueprint if isinstance(blueprint, dict) else {}
    lib = _Lib(library, environment)
    ctx = _Ctx(bp, lib)
    reqs: list[dict] = []
    malformed = ctx.malformed

    def add(kind: str, ref: str, pointer: str, item: dict, candidates: list, claim_keys: list, missing: dict | None = None):
        d = ctx.decide(ref, candidates, claim_keys, missing, _prefer(item))
        reasons = d["reasons"]
        reqs.append({
            "id": f"{kind}:{ref}", "kind": kind, "kind_key": f"gap.kind.{kind}", "kind_labels": _lab(f"gap.kind.{kind}"),
            "ref": ref, "subject_labels": _labels(item), "status": d["status"], "status_key": f"gap.status.{d['status']}",
            "status_labels": _lab(f"gap.status.{d['status']}"), "reasons": reasons, "match": d["match"],
            "alternatives": d["alternatives"], "evidence": _evidence(pointer, item, d["match"]),
        })

    # 1. e-invoicing: the named component must exist and provide a compliance capability
    comp = bp.get("compliance") if isinstance(bp.get("compliance"), dict) else {}
    ei = comp.get("eInvoicing")
    if isinstance(ei, dict) and ei.get("mode") not in (None, "none"):
        cid = _s(ei.get("componentId"))
        mode = _s(ei.get("mode")) or "unknown"
        if cid is None:
            add("compliance", f"einvoicing.{mode}", "/compliance/eInvoicing", ei, [], [], _reason("no_component_named"))
        else:
            cands = lib.component_candidates(cid, "compliance.")
            add("compliance", f"einvoicing.{mode}", "/compliance/eInvoicing", ei, cands, [("component", cid)],
                _reason("component_unknown", component=cid))
    # 2. component bindings
    for cid in sorted(ctx.bindings):
        b = ctx.bindings[cid][0]
        cands = lib.component_candidates(cid)
        add("component", cid, f"/components/{_index(bp, 'components', cid)}", b, cands, [("component", cid)],
            _reason("component_unknown", component=cid))
    # 3. entities, workflows, reports: an artifact of the same type and id must be provided
    for coll, atype in (("entities", "entity"), ("workflows", "workflow"), ("reports", "report")):
        seen = set()
        items = bp.get(coll)
        for i, it in enumerate(items if isinstance(items, list) else []):
            ref = _s(it.get("id")) if isinstance(it, dict) else None
            if ref is None:
                malformed += 1
                continue
            if ref in seen:  # a repeated id is one requirement
                continue
            seen.add(ref)
            add(atype, ref, f"/{coll}/{i}", it, lib.artifact_candidates(atype, ref), [(atype, ref)])
    reqs.sort(key=lambda r: (KIND_ORDER[r["kind"]], r["ref"]))
    counts = {s: sum(1 for r in reqs if r["status"] == s) for s in STATUSES}
    requests = []
    for r in reqs:
        if r["status"] == "uncovered" and r["kind"] != "component":
            requests.append({
                "request_key": hashlib.sha256(r["id"].encode("utf-8")).hexdigest()[:16],
                "requirement_id": r["id"], "kind": r["kind"], "ref": r["ref"],
                "kind_hint": "rigid" if r["kind"] == "compliance" else "configurable",
                "reason_codes": [x["code"] for x in r["reasons"]], "evidence": [e for e in r["evidence"] if e["kind"] != "manifest"],
            })
    return {
        "schema": SCHEMA_VERSION, "environment": environment,
        "blueprint": {"id": _s(_dig(bp, "meta", "id")), "revision": _dig(bp, "meta", "revision") if isinstance(_dig(bp, "meta", "revision"), int) else None},
        "summary": {"total": len(reqs), **counts, "malformed_blueprint_items": malformed,
                    "library_entries_rejected": lib.rejected,
                    "labels": {s: _lab(f"gap.summary.{s}") for s in STATUSES}},
        "requirements": reqs, "component_requests": requests,
    }


def _dig(d: Any, *path: str) -> Any:
    for p in path:
        d = d.get(p) if isinstance(d, dict) else None
    return d


def _index(bp: dict, coll: str, cid: str) -> int:
    for i, c in enumerate(bp.get(coll) or []):
        if isinstance(c, dict) and c.get("id") == cid:
            return i
    return 0


def _prefer(item: dict) -> frozenset:
    cs = item.get("components")
    return frozenset(c["component"] for c in cs if isinstance(c, dict) and _s(c.get("component")) and c.get("mode") == "implements") if isinstance(cs, list) else frozenset()
