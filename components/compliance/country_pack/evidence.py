"""Shared per-fact evidence traversal and production locked-path checks (CMP-035).

The shipped-pack tests share traversal and source rules with production. A sign-off never changes
a fact's label; production requires usable coverage and refuses UNVERIFIED locked facts.
"""

from datetime import date
import re
from typing import Any
from urllib.parse import urlsplit

EVIDENCE_LABELS = {"VERIFIED-OFFICIAL", "SECONDARY", "UNVERIFIED", "PLATFORM-DEFAULT"}
SOURCED_LABELS = {"VERIFIED-OFFICIAL", "SECONDARY"}

MINIMUM_LOCKED_PATHS = ("tax", "eInvoicing", "payrollHooks")

ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# A source that was not read in full (a snippet, a search excerpt, not fetched) carries `"read": false`
# and no access date; every other source carries an access date. This note pattern is only a backstop
# that catches a read source whose note says otherwise.
UNREAD_NOTE = re.compile(r"snippet|excerpt|not (fetched|read)", re.I)


def leaves(obj, prefix: str = ""):
    """(dotted path, value) for every leaf; lists are leaves."""
    if isinstance(obj, dict):
        for key, val in obj.items():
            yield from leaves(val, f"{prefix}.{key}" if prefix else key)
    else:
        yield prefix, obj


def get(obj: dict, dotted: str):
    """Resolve an existing dotted path with nonnegative list indices; otherwise raise KeyError."""
    for part in dotted.split("."):
        segment = re.fullmatch(r"([^\[\]]+)(?:\[(0|[1-9][0-9]*)\])?", part)
        if segment is None or not isinstance(obj, dict) or segment[1] not in obj:
            raise KeyError(dotted)
        obj = obj[segment[1]]
        if segment[2] is not None:
            # Reject out-of-range indices before conversion, including arbitrarily long input.
            if not isinstance(obj, list) or len(segment[2]) > len(str(len(obj))) or int(segment[2]) >= len(obj):
                raise KeyError(dotted)
            obj = obj[int(segment[2])]
    return obj


def source_violations(src: dict, today: str) -> list[str]:
    """Structural read rule: `"read": false` and an access date never go together, and one of them is set."""
    bad = []
    if not isinstance(src, dict):
        return ["source must be an object"]
    url = src.get("url")
    try:
        parsed = urlsplit(url) if isinstance(url, str) else None
        valid_url = (parsed is not None and parsed.scheme == "https" and bool(parsed.hostname)
                     and not any(char.isspace() for char in url))
    except ValueError:
        valid_url = False
    if not valid_url:
        bad.append(f"{src.get('url')!r}: not an https URL")
    label = src.get("url")
    if "read" in src and src["read"] is not False:
        bad.append(f"{label}: read may only be false")
    if src.get("read") is False:
        if "accessed" in src:
            bad.append(f"{label}: unread source has an access date")
        if not src.get("note"):
            bad.append(f"{label}: unread source needs a note saying why")
        return bad
    accessed = src.get("accessed")
    if not isinstance(accessed, str) or not ISO_DATE.fullmatch(accessed):
        bad.append(f"{label}: read source needs an ISO access date (or read: false)")
    else:
        try:
            date.fromisoformat(accessed)
        except ValueError:
            bad.append(f"{label}: read source needs a valid ISO access date")
        else:
            if accessed > today:
                bad.append(f"{label}: access date in the future")
    if UNREAD_NOTE.search(str(src.get("note", ""))):
        bad.append(f"{label}: note says unread but the source is not marked read: false")
    return bad


def fact_source_violations(fact: dict, today: str) -> list[str]:
    """Share source, read-source and platform-reference rules between shipped tests and runtime."""
    sources = fact.get("sources", [])
    if not isinstance(sources, list):
        return ["sources must be a list"]
    bad = [reason for source in sources for reason in source_violations(source, today)]
    if fact["status"] in SOURCED_LABELS and not any(
        isinstance(source, dict) and "accessed" in source for source in sources
    ):
        bad.append(f"{fact['status']} needs a read source with an access date")
    if fact["status"] == "PLATFORM-DEFAULT" and not fact.get("ref"):
        bad.append("PLATFORM-DEFAULT needs a ref")
    return bad


def covered(leaf: str, paths: list[str]) -> bool:
    """Return whether a dotted path is at or beneath an evidenced or locked path."""
    return any(leaf == p or leaf.startswith((f"{p}.", f"{p}[")) for p in paths)


def evidence_entries(evidence: dict):
    """Yield stable ids and entries for facts, blockers and facts outside the pack schema."""
    for fact in evidence["facts"]:
        yield "|".join(fact["paths"]), fact
    for blocker in evidence.get("goLiveBlockers", []):
        yield f"blocker:{blocker['id']}", blocker
    for idx, fact in enumerate(evidence.get("factsOutsideSchema", [])):
        yield f"outside:{idx}", fact


def labelled(evidence: dict, label: str) -> set[str]:
    """Return stable entry ids claiming a label, used by the reviewed source-label snapshots."""
    return {eid for eid, entry in evidence_entries(evidence) if entry["status"] == label}


def locked_fact_refusals(pack: dict[str, Any], evidence: dict[str, Any]) -> list[str]:
    """Require usable evidence for every present locked leaf and refuse UNVERIFIED overlaps.

    Override-policy locale paths are relative to localeDefaults; other locked paths are pack roots.
    Always lock tax, eInvoicing and payrollHooks. Lists (including empty lists) and nulls are leaves,
    matching the shipped packs. Evidence may name the leaf or an ancestor; indexed facts alone do
    not cover a whole list. Unknown fact paths are refused even outside locked areas.
    """
    facts = evidence.get("facts")
    if not isinstance(facts, list) or not facts:
        return ["evidence.json.facts: must be a nonempty list of labelled facts"]
    locked = sorted(set(MINIMUM_LOCKED_PATHS) | {
        p if p.split(".")[0] in pack else f"localeDefaults.{p}"
        for p in pack["overridesPolicy"]["lockedPaths"]
    })
    reasons = []
    evidenced = []
    for index, fact in enumerate(facts):
        prefix = f"evidence.json.facts[{index}]"
        if not isinstance(fact, dict):
            reasons.append(f"{prefix}: must be an object")
            continue
        paths = fact.get("paths")
        if not isinstance(paths, list) or not paths or not all(isinstance(p, str) and p for p in paths):
            reasons.append(f"{prefix}.paths: must name pack paths")
            continue
        status = fact.get("status")
        if not isinstance(status, str) or status not in EVIDENCE_LABELS:
            reasons.append(f"{prefix}.status: must be a known evidence label")
            continue
        for path in paths:
            try:
                get(pack, path)
            except KeyError:
                reasons.append(f"{prefix}.paths: pack path {path} does not exist")
                continue
            # A whole-area fact can back a locked descendant; check both overlap directions.
            if covered(path, locked) or any(covered(p, [path]) for p in locked):
                if status == "UNVERIFIED":
                    reasons.append(f"{prefix}: UNVERIFIED fact on locked path {path}")
            if status != "UNVERIFIED":
                evidenced.append(path)
        if status in SOURCED_LABELS or status == "PLATFORM-DEFAULT":
            reasons.extend(f"{prefix}: {reason}" for reason in fact_source_violations(fact, date.today().isoformat()))
    for path in locked:
        try:
            value = get(pack, path)
        except KeyError:
            reasons.append(f"overridesPolicy.lockedPaths: locked path {path} does not exist")
            continue
        for leaf, _ in leaves(value, path):
            if not covered(leaf, evidenced):
                reasons.append(f"evidence.json.facts: locked leaf {leaf} has no non-UNVERIFIED evidence coverage")
    return reasons
