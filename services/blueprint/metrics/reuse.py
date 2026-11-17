"""Component reuse ratio and new components per build (BPL-022). Pure, no I/O, inputs never modified."""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from .autonomy import _percent
from .errors import MetricsError


@dataclass(frozen=True)
class ReuseResult:
    reused: int                      # components used by 2+ tenants
    total: int                       # all components in use
    percent: float
    tenant_counts: dict[str, int]    # component id -> number of distinct tenants (sorted by id)
    reused_ids: tuple[str, ...]

    @property
    def ratio(self) -> tuple[int, int]:
        return (self.reused, self.total)

    def to_dict(self) -> dict:
        return {"ratio": {"numerator": self.reused, "denominator": self.total}, "percent": self.percent,
                "tenant_counts": dict(self.tenant_counts), "reused_ids": list(self.reused_ids)}


def reuse_ratio(tenants_components: Mapping[str, Iterable[tuple[str, str]]]) -> ReuseResult:
    """Components used by two or more tenants, over all components in use.

    Input: tenant id -> list of (component id, version). Choice: a component is its id; the same id at different
    versions is ONE component (version drift is an upgrade concern, not a new component), and a tenant that uses
    two versions of it counts once for that component. Refuses when no component is in use.
    """
    if not isinstance(tenants_components, Mapping):
        raise MetricsError("MET-REUSE-001", "input is not a mapping tenant -> components")
    users: dict[str, set[str]] = {}
    for tenant, comps in tenants_components.items():
        if not isinstance(tenant, str) or not tenant or isinstance(comps, (str, bytes)) or not isinstance(comps, Iterable):
            raise MetricsError("MET-REUSE-001", "tenant must be a non-empty string mapped to a list of pairs")
        for pair in comps:
            if (not isinstance(pair, (tuple, list)) or len(pair) != 2 or not isinstance(pair[0], str) or not pair[0]
                    or not isinstance(pair[1], str) or not pair[1]):
                raise MetricsError("MET-REUSE-001", f"{tenant}: component entry is not (id, version) of strings")
            users.setdefault(pair[0], set()).add(tenant)
    if not users:
        raise MetricsError("MET-REUSE-002", "no component is in use")
    counts = {c: len(users[c]) for c in sorted(users)}
    reused = tuple(c for c, n in counts.items() if n >= 2)
    return ReuseResult(len(reused), len(counts), _percent(len(reused), len(counts)), counts, reused)


@dataclass(frozen=True)
class NewComponentsResult:
    count: int
    added: tuple[str, ...]
    removed: tuple[str, ...]   # informational, not part of the count

    def to_dict(self) -> dict:
        return {"count": self.count, "added": list(self.added), "removed": list(self.removed)}


def _id_set(ids: Any) -> set[str]:
    if isinstance(ids, (str, bytes, Mapping)) or not isinstance(ids, Iterable):
        raise MetricsError("MET-NEW-001", "expected a collection of component ids")
    out = set()
    for i in ids:
        if not isinstance(i, str) or not i:
            raise MetricsError("MET-NEW-001", "component id is not a non-empty string")
        out.add(i)
    return out


def new_components_per_build(before_registry_ids: Iterable[str], after_registry_ids: Iterable[str]) -> NewComponentsResult:
    """Components added to the library for this build: ids in `after` that were not in `before`.
    Versions of an existing id do not count. Removed ids are reported but never reduce the count."""
    before, after = _id_set(before_registry_ids), _id_set(after_registry_ids)
    added = tuple(sorted(after - before))
    return NewComponentsResult(len(added), added, tuple(sorted(before - after)))
