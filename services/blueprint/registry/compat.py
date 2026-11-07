"""Compatibility of Blueprint component bindings with an engine target (mirrors validator rule 8)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from validator import semver


@dataclass(frozen=True)
class CompatResult:
    """Per-component outcome. `reasons` lists why it failed; `notes` lists things not checked."""

    component: str
    version_range: str
    resolved_version: str | None
    ok: bool
    reasons: tuple = ()
    notes: tuple = ()

    def as_dict(self) -> dict:
        return {"component": self.component, "versionRange": self.version_range, "resolvedVersion": self.resolved_version,
                "ok": self.ok, "reasons": list(self.reasons), "notes": list(self.notes)}


def check_compatibility(registry, blueprint_components: Any, engine_target: Any) -> list[CompatResult]:
    """For each `{id, versionRange}` binding: resolve the highest registry version in the range, then compare the
    manifest's `engineCompatibility.adapter` with `engine_target['adapter']` and `engine_target['versionSet']`
    with `testedAgainst`. As in validator rule 8, `engineRange` is not evaluated (the Blueprint does not state the
    engine's own version). Without an engine target nothing engine-related is checked and a note says so.
    Results are sorted by component id, then range."""
    target = engine_target if isinstance(engine_target, dict) and engine_target else None
    out: list[CompatResult] = []
    items = blueprint_components if isinstance(blueprint_components, (list, tuple)) else []
    for b in items:
        cid = b.get("id") if isinstance(b, dict) else None
        rng = b.get("versionRange") if isinstance(b, dict) else None
        if not isinstance(cid, str) or not isinstance(rng, str):
            out.append(CompatResult(str(cid) if cid is not None else "?", str(rng or ""), None, False,
                                    ("binding needs string 'id' and 'versionRange'",)))
            continue
        if not registry.versions(cid):
            out.append(CompatResult(cid, rng, None, False, (f"component '{cid}' is not in the registry",)))
            continue
        try:
            m = registry.resolve(cid, rng)
        except ValueError:
            out.append(CompatResult(cid, rng, None, False, (f"version range '{rng}' is not valid",)))
            continue
        if m is None:
            have = ", ".join(registry.versions(cid))
            out.append(CompatResult(cid, rng, None, False, (f"no registry version of '{cid}' satisfies '{rng}' (available: {have})",)))
            continue
        reasons, notes = [], []
        if target is None:
            notes.append("engine compatibility not checked: no engine target given")
        else:
            ec = m["engineCompatibility"]
            if ec["adapter"] != target.get("adapter"):
                reasons.append(f"'{cid}' targets adapter '{ec['adapter']}', engine target is '{target.get('adapter')}'")
            vs = target.get("versionSet")
            if isinstance(vs, str) and vs not in ec.get("testedAgainst", []):
                reasons.append(f"'{cid}' is not tested against version set '{vs}'")
            notes.append("engineRange not evaluated")
        out.append(CompatResult(cid, rng, m["version"], not reasons, tuple(reasons), tuple(notes)))
    return sorted(out, key=lambda r: (r.component, r.version_range))
