"""`prevalidate(dataset, config) -> PrevalidationReport`. Pure, deterministic, no I/O.

Dataset: a list of row dicts, or {"rows": [...], "sheet": <default sheet id>}. Rows are
never mutated; quarantined rows are deep-copied intact as evidence with a SHA-256 of their
canonical JSON. A row is quarantined when any blocking finding names it as a primary row.
Rows with only needs_owner findings stay in `accepted` and are listed in `owner_review`.
"""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass

from . import checks
from .config import load_config
from .duplicates import group_duplicates
from .errors import PrevalidationError

VERSION = 1


@dataclass
class PrevalidationReport:
    findings: list
    accepted: list
    quarantine: list
    owner_review: list
    counts: dict
    summary: dict
    name_groups: dict

    def to_dict(self) -> dict:
        return {"version": VERSION, "summary": self.summary, "counts": self.counts,
                "findings": self.findings, "accepted": self.accepted, "quarantine": self.quarantine,
                "owner_review": self.owner_review, "name_groups": self.name_groups}


def row_hash(row) -> str:
    try:
        blob = json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    except (TypeError, ValueError):
        raise PrevalidationError("PRE-E02", "unserialisable")
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _rows(dataset, cfg):
    sheet = None
    if isinstance(dataset, dict):
        if set(dataset) - {"rows", "sheet"} or "rows" not in dataset:
            raise PrevalidationError("PRE-E01")
        sheet = dataset.get("sheet")
        rows = dataset["rows"]
    else:
        rows = dataset
    if not isinstance(rows, (list, tuple)):
        raise PrevalidationError("PRE-E01")
    if len(rows) > cfg.max_rows:
        raise PrevalidationError("PRE-E04", "rows")
    for r in rows:
        if not isinstance(r, dict) or not all(isinstance(k, str) for k in r):
            raise PrevalidationError("PRE-E02")
    return rows, sheet


def _skey(p):
    return (str(p["sheet"]), str(type(p["row"]).__name__), str(p["row"]))


def prevalidate(dataset, config=None) -> PrevalidationReport:
    cfg = load_config(config)
    rows, sheet = _rows(dataset, cfg)
    recs = [checks.build_rec(i, r, cfg, sheet) for i, r in enumerate(rows)]
    found = []
    found += checks.check_required(recs, cfg)
    found += checks.check_amounts_and_signs(recs)
    found += checks.check_dates(recs, cfg)
    found += checks.check_totals(recs, cfg)
    found += checks.check_duplicates(recs, cfg)
    found += checks.check_currency(recs)
    found += checks.check_stock(recs, cfg)
    groups = {}
    for code, key, fld in (("PRE-801", "party", "party"), ("PRE-802", "item", "item")):
        col = cfg.fields[fld]
        names = [r.get(col) if isinstance(r.get(col), str) else "" for r in rows]
        g = group_duplicates(names, cfg.name_threshold)
        groups[key] = g
        for grp in g:
            members = {m["name"] for m in grp["members"]}
            idxs = [i for i, n in enumerate(names) if n in members]
            found.append(checks.Finding(code, idxs, params={"canonical": grp["canonical"], "rule": grp["rule"],
                                                            "variants": [m["name"] for m in grp["members"]]}))
    ptr = lambda i: recs[i].ptr
    found.sort(key=lambda f: (checks.SEV[f.severity], f.code, min(f.rows) if f.rows else -1, f.rows))
    out, q_idx, owner_idx = [], {}, set()
    for n, f in enumerate(found, 1):
        name, sev = checks.CODES[f.code]
        blocking = sev == "blocking"
        out.append({
            "id": f"F{n:04d}", "code": f.code, "severity": sev, "reason_key": f"pre.{name}",
            "rows": sorted((ptr(i) for i in f.rows), key=_skey),
            "related_rows": sorted((ptr(i) for i in f.related), key=_skey),
            "params": f.params, "quarantined": blocking,
        })
        for i in f.rows:
            if blocking:
                q_idx.setdefault(i, []).append(f.code)
            elif sev == "needs_owner":
                owner_idx.add(i)
    counts = {}
    for f in out:
        counts[f["code"]] = counts.get(f["code"], 0) + 1
    accepted = [copy.deepcopy(rows[i]) for i in range(len(rows)) if i not in q_idx]
    quarantine = [{"pointer": ptr(i), "finding_codes": sorted(set(c)), "sha256": row_hash(rows[i]),
                   "row": copy.deepcopy(rows[i])} for i, c in sorted(q_idx.items())]
    owner = [ptr(i) for i in sorted(owner_idx - set(q_idx))]
    summary = {"rows": len(rows), "accepted": len(accepted), "quarantined": len(quarantine),
               "owner_review": len(owner), "findings": len(out)}
    return PrevalidationReport(out, accepted, quarantine, owner, dict(sorted(counts.items())), summary, groups)
