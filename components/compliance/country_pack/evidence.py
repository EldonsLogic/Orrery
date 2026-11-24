"""Shared per-fact evidence traversal and production locked-path checks (CMP-035).

The shipped-pack tests pin sourced labels through these same traversal helpers. A sign-off never
changes a fact's label; production refuses UNVERIFIED facts wherever they overlap a locked path.
"""

from typing import Any

EVIDENCE_LABELS = {"VERIFIED-OFFICIAL", "SECONDARY", "UNVERIFIED", "PLATFORM-DEFAULT"}


def covered(leaf: str, paths: list[str]) -> bool:
    """Return whether a dotted path is at or beneath an evidenced or locked path."""
    return any(leaf == p or leaf.startswith(f"{p}.") for p in paths)


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
    """Reject unusable fact records and UNVERIFIED facts overlapping the pack's locked paths.

    Override-policy locale paths are relative to localeDefaults; other locked paths are pack roots.
    Check both directions so a fact backing a whole area cannot hide a locked descendant.
    """
    facts = evidence.get("facts")
    if not isinstance(facts, list) or not facts:
        return ["evidence.json.facts: must be a nonempty list of labelled facts"]
    locked = [p if p.split(".")[0] in pack else f"localeDefaults.{p}"
              for p in pack["overridesPolicy"]["lockedPaths"]]
    reasons = []
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
        elif status == "UNVERIFIED":
            for path in paths:
                if covered(path, locked) or any(covered(p, [path]) for p in locked):
                    reasons.append(f"{prefix}: UNVERIFIED fact on locked path {path}")
    return reasons
