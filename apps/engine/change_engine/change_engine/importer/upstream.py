"""Bounded server-side DSC-019 report verification."""
from __future__ import annotations

import hashlib
from collections import Counter
from decimal import Context, Decimal, localcontext

from services.discovery.prevalidate import PrevalidationError, prevalidate

from .errors import ImportFailure

# DSC-019 accumulates findings and compares names pairwise. Bound each invocation
# before calling it; public errors are separately fail-fast (one safe error).
MAX_PREVALIDATION_ROWS = 250


def _valid_name_group(group) -> bool:
    return (isinstance(group, dict)
            and set(group) == {"canonical", "members", "keys", "rule", "needs_owner_confirmation"}
            and isinstance(group["canonical"], str) and isinstance(group["rule"], str)
            and group["needs_owner_confirmation"] is True
            and isinstance(group["keys"], list) and all(isinstance(k, str) for k in group["keys"])
            and isinstance(group["members"], list) and len(group["members"]) >= 2
            and all(isinstance(m, dict) and isinstance(m.get("name"), str) for m in group["members"]))


def check_report(report, source_rows, *, allow_name_groups: bool = False, bounded_fn=None, canonical_fn=None, fail_fn=None):
    """Consume DSC-019 v1 without adopting suggestions or dropping quarantine.

    Matching row multisets detect a report reused for different data, including
    missing quarantined rows. When allow_name_groups is True, unblocked PRE-801/
    PRE-802 name-group findings are accepted structurally for downstream server
    verification and owner confirmation checking.
    """
    try:
        if isinstance(report, str):
            report = json_loads_decimal(report)
        required = {"version", "summary", "counts", "findings", "accepted", "quarantine", "owner_review", "name_groups"}
        if (not isinstance(report, dict) or set(report) != required
                or type(report["version"]) is not int or report["version"] != 1):
            fail_fn("IMP-REPORT")
        bounded_fn(report)
        for key in ("findings", "accepted", "quarantine", "owner_review"):
            if not isinstance(report[key], list):
                fail_fn("IMP-REPORT")
        if (not isinstance(report["name_groups"], dict) or set(report["name_groups"]) != {"party", "item"}
                or any(not isinstance(g, list) for g in report["name_groups"].values())):
            fail_fn("IMP-REPORT")
        counts_summary = {
            "quarantined": len(report["quarantine"]), "owner_review": len(report["owner_review"]),
            "findings": len(report["findings"]),
            "duplicate_groups": sum(len(g) if isinstance(g, list) else 1 for g in report["name_groups"].values()),
        }
        if report["quarantine"]:
            raise ImportFailure("IMP-REPORT", report_counts=counts_summary)
        if not allow_name_groups:
            if report["owner_review"] or any(report["name_groups"].values()) or report["findings"]:
                raise ImportFailure("IMP-REPORT", report_counts=counts_summary)
        else:
            expected_owner = set()
            for finding in report["findings"]:
                if (not isinstance(finding, dict) or finding.get("code") not in {"PRE-801", "PRE-802"}
                        or finding.get("severity") != "needs_owner" or finding.get("quarantined") is not False
                        or not isinstance(finding.get("rows"), list)
                        or not all(isinstance(ptr, dict) for ptr in finding["rows"])):
                    raise ImportFailure("IMP-REPORT", report_counts=counts_summary)
                expected_owner.update(canonical_fn(ptr) for ptr in finding["rows"])
            if (not all(isinstance(ptr, dict) for ptr in report["owner_review"])
                    or Counter(canonical_fn(ptr) for ptr in report["owner_review"]) != Counter(expected_owner)
                    or any(not _valid_name_group(g) for lst in report["name_groups"].values() for g in lst)):
                raise ImportFailure("IMP-REPORT", report_counts=counts_summary)
            if report["findings"] and not any(report["name_groups"].values()):
                raise ImportFailure("IMP-REPORT", report_counts=counts_summary)
        expected = {"rows": len(source_rows), "accepted": len(source_rows), "quarantined": 0,
                    "owner_review": len(report["owner_review"]), "findings": len(report["findings"])}
        if (report["summary"] != expected or any(type(v) is not int for v in report["summary"].values())
                or report["counts"] != dict(Counter(f["code"] for f in report["findings"]))
                or Counter(canonical_fn(r) for r in report["accepted"]) != Counter(canonical_fn(r) for r in source_rows)):
            fail_fn("IMP-REPORT")
        return report
    except (TypeError, ValueError, KeyError, RecursionError):
        fail_fn("IMP-REPORT")


def json_loads_decimal(raw: str):
    import json
    return json.loads(raw, parse_float=Decimal)


def verify_upstream(datasets, meta, *, bounded_fn, canonical_fn, fail_fn):
    """Re-run DSC-019 on submitted rows with server-owned master name mappings.

    Near-duplicate checks run on master name fields only, never detail links or
    codes. Returns detected name groups for server-verified owner confirmation.
    """
    mappings = {"Customer": {"party": "customer_name"}, "Supplier": {"party": "supplier_name"},
                "Item": {"item": "item_name"}}
    detected_groups = []
    try:
        with localcontext(Context(prec=128)):
            for entity, dataset in sorted(datasets.items()):
                raw = dataset["rows"] if isinstance(dataset, dict) else dataset
                if len(raw) > MAX_PREVALIDATION_ROWS:
                    fail_fn("IMP-LIMIT")
                config = {"required": {"*": []}, "fields": {"date": "posting_date", **mappings.get(entity, {})},
                          "max_rows": MAX_PREVALIDATION_ROWS}
                # Upper-bound pairwise edit-distance work before the upstream API
                # allocates groups/findings. Raw name lengths are conservative.
                work = 0
                for field in (config["fields"].get("party", "party"), config["fields"].get("item", "item")):
                    lengths = [len(name) for name in {r.get(field) for r in raw} if isinstance(name, str)]
                    work += (sum(lengths) ** 2 - sum(n * n for n in lengths)) // 2
                if work > 2_000_000:
                    fail_fn("IMP-LIMIT")
                # Missing per-row date/currency inherits the validated batch context.
                rows = [{"posting_date": meta["posting_date"], "currency": meta["currency"], **r} for r in raw]
                generated = prevalidate(rows, config).to_dict()
                check_report(
                    generated, rows, allow_name_groups=True,
                    bounded_fn=bounded_fn, canonical_fn=canonical_fn, fail_fn=fail_fn,
                )
                for kind in ("party", "item"):
                    for grp in generated["name_groups"][kind]:
                        members = sorted(m["name"] for m in grp["members"])
                        gid = hashlib.sha256(
                            canonical_fn({"entity": entity, "rule": grp["rule"], "members": members}).encode("utf-8")
                        ).hexdigest()
                        detected_groups.append({
                            "id": gid, "entity": entity, "kind": kind,
                            "rule": grp["rule"], "members": members,
                        })
        return detected_groups
    except PrevalidationError:
        fail_fn("IMP-REPORT")
