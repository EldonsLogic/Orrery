"""The component registry: an in-memory, read-only view over admitted manifests."""
from __future__ import annotations

import copy
import os
from typing import Any

from validator import semver

from .admission import admit, version_key
from .compat import CompatResult, check_compatibility
from .issues import Issue
from .store import ID_RE, DirectoryStore, ManifestStore, RawManifest


class Registry:
    """Build with `Registry.load(dir)`, `Registry.from_store(store)` or `Registry.from_manifests(list)`.

    Only manifests that passed admission are visible. Findings (errors, warnings) are in `issues`.
    Every getter returns copies and deterministic (sorted) results.
    """

    def __init__(self, manifests: list[dict], issues: list[Issue], strict: bool = False):
        self._by_id: dict[str, dict[str, dict]] = {}
        for m in manifests:
            self._by_id.setdefault(m["id"], {})[m["version"]] = m
        self.issues: list[Issue] = list(issues)
        self.strict = strict

    # construction
    @classmethod
    def from_store(cls, store: ManifestStore, strict: bool = False) -> "Registry":
        admitted, issues = admit(store.read_all(), strict=strict)
        return cls(admitted, issues, strict)

    @classmethod
    def load(cls, directory: str | os.PathLike, strict: bool = False) -> "Registry":
        """Load a folder of manifest files. Raises OSError if the folder cannot be listed."""
        return cls.from_store(DirectoryStore(directory), strict=strict)

    @classmethod
    def from_manifests(cls, manifests: list[Any], strict: bool = False) -> "Registry":
        raws = [RawManifest(f"manifest[{i}]", m) for i, m in enumerate(manifests)]
        admitted, issues = admit(raws, strict=strict)
        return cls(admitted, issues, strict)

    # findings
    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.is_error]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if not i.is_error]

    @property
    def ok(self) -> bool:
        return not self.errors

    # queries
    def list_components(self) -> list[str]:
        return sorted(self._by_id)

    def versions(self, component_id: str) -> list[str]:
        """Versions of a component, lowest to highest by semver precedence. Unknown or malformed id: empty list."""
        if not isinstance(component_id, str) or not ID_RE.match(component_id):
            return []
        return sorted(self._by_id.get(component_id, {}), key=version_key)

    def get(self, component_id: str, version: str) -> dict | None:
        if not isinstance(component_id, str) or not ID_RE.match(component_id):
            return None
        m = self._by_id.get(component_id, {}).get(version) if isinstance(version, str) else None
        return copy.deepcopy(m) if m is not None else None

    def resolve(self, component_id: str, version_range: str) -> dict | None:
        """Highest version inside the range, or None. An invalid range raises ValueError."""
        best = semver.highest_satisfying(self.versions(component_id), version_range)
        return self.get(component_id, best) if best else None

    def provides(self, name: str) -> list[tuple[str, str]]:
        """(component id, version) pairs, sorted, of every manifest that provides the capability `name` or a
        `function` artifact whose ref is `name`."""
        out = []
        for cid in self.list_components():
            for v in self.versions(cid):
                for p in self._by_id[cid][v]["provides"]:
                    if p["capability"] == name or any(a["type"] == "function" and a["ref"] == name for a in p["artifacts"]):
                        out.append((cid, v))
                        break
        return out

    def as_validation_context_registry(self) -> dict[str, list[dict]]:
        """Shape of `ValidationContext.registry`: component id -> list of manifests (lowest version first)."""
        return {cid: [copy.deepcopy(self._by_id[cid][v]) for v in self.versions(cid)] for cid in self.list_components()}

    def compatible(self, blueprint_components: Any, engine_target: Any) -> list[CompatResult]:
        return check_compatibility(self, blueprint_components, engine_target)
