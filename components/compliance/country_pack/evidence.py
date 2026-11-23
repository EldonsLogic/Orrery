"""Shared per-fact evidence traversal and production locked-path checks (CMP-035).

The shipped-pack tests share traversal and source rules with production. A sign-off never changes
a fact's label; production requires usable coverage and refuses UNVERIFIED locked facts.
"""

from datetime import date
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlsplit

from .strict_json import loads_strict

EVIDENCE_LABELS = {"VERIFIED-OFFICIAL", "SECONDARY", "UNVERIFIED", "PLATFORM-DEFAULT"}
SOURCED_LABELS = {"VERIFIED-OFFICIAL", "SECONDARY"}

MINIMUM_LOCKED_PATHS = ("tax", "eInvoicing", "payrollHooks")

# Every key evidence.json may carry (CMP-036). Anything else is refused in production.
EVIDENCE_TOP_LEVEL_KEYS = frozenset({
    "packId", "version", "purpose", "facts", "factsOutsideSchema", "pendingRefs", "goLiveBlockers",
    "arabicLabels", "arabicReviewNote", "certification",
})
# Per-market product-choice paths a PLATFORM-DEFAULT fact may back (ADR-0067); data, not code.
PRODUCT_CHOICE_FILE = Path(__file__).resolve().parent / "product_choice_paths.json"
# The project's first work is dated 2026-11 (docs/log); no read source can predate this floor.
ACCESS_DATE_FLOOR = "2026-01-01"
RESOLUTION_KEYS = frozenset({"status", "by", "at"})

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
            elif accessed < ACCESS_DATE_FLOOR:
                bad.append(f"{label}: access date before {ACCESS_DATE_FLOOR}")
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
    ref = fact.get("ref")
    if fact["status"] == "PLATFORM-DEFAULT" and not (isinstance(ref, str) and ref.strip()):
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


def product_choice_entries() -> dict[str, list[dict[str, str]]]:
    """Return the reviewed per-market product-choice list; raise ValueError if the file is unusable."""
    try:
        data = loads_strict(PRODUCT_CHOICE_FILE.read_text(encoding="utf-8"))
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"{PRODUCT_CHOICE_FILE.name} unreadable") from exc
    if not isinstance(data, dict) or set(data) - {"description", "markets"} or not isinstance(data.get("markets"), dict):
        raise ValueError("expected an object with 'markets' (and optional 'description')")
    markets: dict[str, list[dict[str, str]]] = {}
    for market, entries in data["markets"].items():
        if not (isinstance(market, str) and re.fullmatch(r"[A-Z]{2}", market) and isinstance(entries, list)):
            raise ValueError(f"market {market!r} must be a two-letter code with a list of entries")
        for entry in entries:
            ok = (isinstance(entry, dict) and {"path", "reason"} <= set(entry) <= {"path", "reason", "provisional"}
                  and all(isinstance(v, str) and v.strip() for v in entry.values()))
            # At least two segments: a top-level area such as `tax` is never listable.
            if not ok or not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*(\.[A-Za-z][A-Za-z0-9]*)+", entry["path"]):
                raise ValueError(f"market {market}: invalid entry {entry!r}")
        markets[market] = entries
    return markets


def is_product_choice_path(listed: list[str], path: str) -> bool:
    """A path is allowed if it equals a listed path or lies beneath one; never through an ancestor."""
    return covered(path, listed)


def locked_paths(pack: dict[str, Any]) -> list[str]:
    """Pack-root dotted locked paths: the minimum areas plus the pack's own policy (locale ones relative)."""
    return sorted(set(MINIMUM_LOCKED_PATHS) | {
        p if p.split(".")[0] in pack else f"localeDefaults.{p}"
        for p in pack["overridesPolicy"]["lockedPaths"]
    })


def _overlaps_locked(path: str, locked: list[str]) -> bool:
    # A whole-area fact can back a locked descendant; check both overlap directions.
    return covered(path, locked) or any(covered(p, [path]) for p in locked)


def locked_fact_refusals(pack: dict[str, Any], evidence: dict[str, Any]) -> list[str]:
    """Require usable evidence for every present locked leaf and refuse UNVERIFIED overlaps.

    Override-policy locale paths are relative to localeDefaults; other locked paths are pack roots.
    Always lock tax, eInvoicing and payrollHooks. Lists (including empty lists) and nulls are leaves,
    matching the shipped packs. Evidence may name the leaf or an ancestor; indexed facts alone do
    not cover a whole list. Unknown fact paths are refused even outside locked areas. A PLATFORM-DEFAULT
    fact on a locked path needs that path (or a path beneath a listed one) on the market's product-choice list
    (ADR-0067); and `verified_official` needs official facts (or listed defaults) under every locked leaf.
    """
    facts = evidence.get("facts")
    if not isinstance(facts, list) or not facts:
        return ["evidence.json.facts: must be a nonempty list of labelled facts"]
    locked = locked_paths(pack)
    reasons = []
    try:
        listed = [e["path"] for e in product_choice_entries().get(pack["countryCode"], [])]
    except ValueError as exc:
        reasons.append(f"product-choice list unusable: {exc}")
        listed = []
    evidenced: list[str] = []
    official: list[str] = []
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
            on_locked = _overlaps_locked(path, locked)
            if on_locked and status == "UNVERIFIED":
                reasons.append(f"{prefix}: UNVERIFIED fact on locked path {path}")
            if on_locked and status == "PLATFORM-DEFAULT" and not is_product_choice_path(listed, path):
                reasons.append(f"{prefix}: PLATFORM-DEFAULT fact on locked path {path} is not on the "
                               f"{pack['countryCode']} product-choice list (ADR-0067)")
                continue
            if status != "UNVERIFIED":
                evidenced.append(path)
            if status == "VERIFIED-OFFICIAL" or (status == "PLATFORM-DEFAULT" and is_product_choice_path(listed, path)):
                official.append(path)
        if status in SOURCED_LABELS or status == "PLATFORM-DEFAULT":
            reasons.extend(f"{prefix}: {reason}" for reason in fact_source_violations(fact, date.today().isoformat()))
    soft = []
    for path in locked:
        try:
            value = get(pack, path)
        except KeyError:
            reasons.append(f"overridesPolicy.lockedPaths: locked path {path} does not exist")
            continue
        for leaf, _ in leaves(value, path):
            if not covered(leaf, evidenced):
                reasons.append(f"evidence.json.facts: locked leaf {leaf} has no non-UNVERIFIED evidence coverage")
            elif not covered(leaf, official):
                soft.append(leaf)
    if soft and pack["evidenceStatus"] == "verified_official":
        reasons.append(f"evidenceStatus verified_official, but {len(soft)} locked leaves rest only on SECONDARY "
                       f"facts (first: {', '.join(soft[:5])})")
    return reasons


def _entry_list(evidence: dict[str, Any], key: str, reasons: list[str]) -> list[Any]:
    value = evidence.get(key, [])
    if not isinstance(value, list):
        reasons.append(f"evidence.json.{key}: must be a list")
        return []
    return value


def resolution_refusals(prefix: str, entry: Any, founders: set[str] | None) -> list[str]:
    """An entry stops blocking only with `resolution` {status: resolved, by: founder login, at: date}."""
    if not isinstance(entry, dict):
        return [f"{prefix}: must be an object"]
    if "resolution" not in entry:
        return [f"{prefix}: open (no resolution record)"]
    record = entry["resolution"]
    if not isinstance(record, dict) or set(record) != RESOLUTION_KEYS:
        return [f"{prefix}.resolution: must be an object with exactly status, by and at"]
    bad = []
    if record["status"] != "resolved":
        bad.append(f"{prefix}.resolution.status: only 'resolved' stops blocking")
    by = record["by"]
    if founders is not None and not (isinstance(by, str) and by.casefold() in founders):
        bad.append(f"{prefix}.resolution.by: must be a founder GitHub login")
    at = record["at"]
    try:
        valid = isinstance(at, str) and ISO_DATE.fullmatch(at) is not None and bool(date.fromisoformat(at))
    except ValueError:
        valid = False
    if not valid:
        bad.append(f"{prefix}.resolution.at: must be a valid YYYY-MM-DD date")
    elif at > date.today().isoformat():
        bad.append(f"{prefix}.resolution.at: date in the future")
    elif at < ACCESS_DATE_FLOOR:
        bad.append(f"{prefix}.resolution.at: date before {ACCESS_DATE_FLOOR}")
    return bad


def blocker_refusals(pack: dict[str, Any], evidence: dict[str, Any], founders: set[str] | None) -> list[str]:
    """Open `goLiveBlockers` / `pendingRefs` and UNVERIFIED `factsOutsideSchema` on locked paths (ADR-0067).

    `founders` is the casefolded founder login set, or None when the founders map is unusable (that is
    refused elsewhere; resolution authors cannot be checked then).
    """
    reasons: list[str] = []
    for key in ("goLiveBlockers", "pendingRefs"):
        for index, entry in enumerate(_entry_list(evidence, key, reasons)):
            reasons.extend(resolution_refusals(f"evidence.json.{key}[{index}]", entry, founders))
    locked = locked_paths(pack)
    for index, fact in enumerate(_entry_list(evidence, "factsOutsideSchema", reasons)):
        prefix = f"evidence.json.factsOutsideSchema[{index}]"
        status = fact.get("status") if isinstance(fact, dict) else None
        if not isinstance(status, str) or status not in EVIDENCE_LABELS:
            reasons.append(f"{prefix}.status: must be a known evidence label")
            continue
        paths = fact.get("paths", [])
        if not isinstance(paths, list) or not all(isinstance(p, str) and p for p in paths):
            reasons.append(f"{prefix}.paths: must be a list of pack paths")
            continue
        for path in paths:
            try:
                get(pack, path)
            except KeyError:
                reasons.append(f"{prefix}.paths: pack path {path} does not exist")
                continue
            if status == "UNVERIFIED" and _overlaps_locked(path, locked):
                reasons.append(f"{prefix}: UNVERIFIED fact on locked path {path}")
        if status in SOURCED_LABELS or status == "PLATFORM-DEFAULT":
            reasons.extend(f"{prefix}: {reason}" for reason in fact_source_violations(fact, date.today().isoformat()))
    return reasons
