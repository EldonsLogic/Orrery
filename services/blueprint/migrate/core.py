"""Migration framework. Error codes:

MIG-INPUT-001 not an object / no meta.schemaVersion      MIG-VER-001 malformed version string
MIG-VER-002 unknown version (no step leaves or enters it) MIG-VER-003 future version (above the latest)
MIG-VER-004 downgrade requested                           MIG-PATH-001 no path (gap)
MIG-REG-001 bad registration (malformed, not upward)      MIG-REG-002 duplicate step from a version
MIG-STATE-001 buildState is not draft and no flag         MIG-STEP-001 step raised or returned a non-object
MIG-STEP-002 step touched meta.revision, id or buildState MIG-STEP-003 step set meta.schemaVersion itself
MIG-VALID-001 migrated document fails the validator at the schema's current version
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from typing import Any, Callable

CURRENT_SCHEMA_VERSION = "0.1.0"  # equals contracts/blueprint.schema.json meta.schemaVersion const
_VER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
_PROTECTED = ("revision", "id", "buildState")
MAX_DEPTH = 64


@dataclass(frozen=True, order=True)
class Issue:
    code: str
    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.code} {self.path or '/'}: {self.message}"


@dataclass(frozen=True)
class StepRecord:
    from_version: str
    to_version: str
    changes: tuple  # tuple of {"path", "op": add|remove|replace, "before"?, "after"?}, sorted by path


@dataclass
class MigrationResult:
    blueprint: dict | None = None
    from_version: str | None = None
    to_version: str | None = None
    steps: list = field(default_factory=list)
    errors: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def noop(self) -> bool:
        return self.ok and not self.steps


def parse_version(v: Any) -> tuple | None:
    if not isinstance(v, str) or len(v) > 32:
        return None
    m = _VER.match(v)
    return tuple(int(x) for x in m.groups()) if m else None


class Registry:
    """Steps keyed by from_version. One step leaves a version, so a path is a single chain: no branches, no cycles."""

    def __init__(self, latest: str = CURRENT_SCHEMA_VERSION) -> None:
        if parse_version(latest) is None:
            raise ValueError("MIG-REG-001 malformed latest version")
        self._steps: dict[str, tuple[str, Callable[[dict], dict]]] = {}
        self._base_latest = latest

    def register(self, from_version: str, to_version: str):
        """Decorator. The step takes a deep copy of the document and returns the migrated document. It must not set
        meta.schemaVersion (the framework does) and must not change meta.revision, meta.id or meta.buildState."""
        a, b = parse_version(from_version), parse_version(to_version)
        if a is None or b is None:
            raise ValueError("MIG-REG-001 malformed version")
        if b <= a:
            raise ValueError("MIG-REG-001 a step must go upward (from < to)")
        if from_version in self._steps:
            raise ValueError("MIG-REG-002 a step from this version is already registered")

        def deco(fn: Callable[[dict], dict]):
            self._steps[from_version] = (to_version, fn)
            return fn
        return deco

    @property
    def latest(self) -> str:
        vs = [self._base_latest] + [t for t, _ in self._steps.values()]
        return max(vs, key=lambda v: parse_version(v))

    def known(self) -> set:
        return {self._base_latest} | set(self._steps) | {t for t, _ in self._steps.values()}

    def path(self, start: str, target: str):
        """Steps from start to target, or an Issue. Walks the single chain; a hop that overshoots is a gap."""
        chain, cur, seen = [], start, {start}
        while cur != target:
            nxt = self._steps.get(cur)
            if nxt is None or parse_version(nxt[0]) > parse_version(target):
                return Issue("MIG-PATH-001", "/meta/schemaVersion", f"no registered path from {start} to {target} (stops at {cur})")
            if nxt[0] in seen:
                return Issue("MIG-PATH-001", "/meta/schemaVersion", "cycle in registered steps")
            seen.add(nxt[0])
            chain.append((cur, nxt[0], nxt[1]))
            cur = nxt[0]
        return chain


REGISTRY = Registry()
register = REGISTRY.register  # module-level decorator on the default registry


def diff_changes(a: Any, b: Any, path: str = "", depth: int = 0) -> list:
    """Deterministic JSON-pointer change list between two documents."""
    if depth > MAX_DEPTH:
        return [{"path": path, "op": "replace", "before": None, "after": None}]
    out: list = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            p = f"{path}/{str(k).replace('~', '~0').replace('/', '~1')}"
            if k not in b:
                out.append({"path": p, "op": "remove", "before": a[k]})
            elif k not in a:
                out.append({"path": p, "op": "add", "after": b[k]})
            else:
                out.extend(diff_changes(a[k], b[k], p, depth + 1))
    elif isinstance(a, list) and isinstance(b, list):
        for i in range(max(len(a), len(b))):
            p = f"{path}/{i}"
            if i >= len(b):
                out.append({"path": p, "op": "remove", "before": a[i]})
            elif i >= len(a):
                out.append({"path": p, "op": "add", "after": b[i]})
            else:
                out.extend(diff_changes(a[i], b[i], p, depth + 1))
    elif a != b or type(a) is not type(b):
        out.append({"path": path, "op": "replace", "before": a, "after": b})
    return out


def _fail(*issues: Issue) -> MigrationResult:
    return MigrationResult(errors=sorted(issues))


def migrate(blueprint: Any, target_version: str | None = None, *, allow_non_draft: bool = False,
            registry: Registry | None = None, validate_result: bool = True) -> MigrationResult:
    """Migrate a copy of `blueprint` to `target_version` (default: latest). Never mutates the input, never raises."""
    reg = registry or REGISTRY
    try:
        return _migrate(blueprint, target_version, allow_non_draft, reg, validate_result)
    except RecursionError:
        return _fail(Issue("MIG-INPUT-001", "/", "document nested too deeply"))
    except Exception as exc:  # fail closed
        return _fail(Issue("MIG-STEP-001", "/", f"migration failed to run ({type(exc).__name__})"))


def _migrate(blueprint, target, allow_non_draft, reg, validate_result) -> MigrationResult:
    meta = blueprint.get("meta") if isinstance(blueprint, dict) else None
    if not isinstance(meta, dict) or "schemaVersion" not in meta:
        return _fail(Issue("MIG-INPUT-001", "/meta/schemaVersion", "document has no meta.schemaVersion"))
    start = meta["schemaVersion"]
    if parse_version(start) is None:
        return _fail(Issue("MIG-VER-001", "/meta/schemaVersion", "schemaVersion is not X.Y.Z"))
    if target is None:
        target = reg.latest
    elif parse_version(target) is None:
        return _fail(Issue("MIG-VER-001", "/", "target version is not X.Y.Z"))
    latest = parse_version(reg.latest)
    if parse_version(start) > latest:
        return _fail(Issue("MIG-VER-003", "/meta/schemaVersion", f"{start} is newer than the latest known version {reg.latest}"))
    if parse_version(target) > latest:
        return _fail(Issue("MIG-VER-003", "/", f"target {target} is newer than the latest known version {reg.latest}"))
    if start not in reg.known():
        return _fail(Issue("MIG-VER-002", "/meta/schemaVersion", f"{start} is not a known version"))
    if target not in reg.known():
        return _fail(Issue("MIG-VER-002", "/", f"target {target} is not a known version"))
    if parse_version(target) < parse_version(start):
        return _fail(Issue("MIG-VER-004", "/", f"downgrade {start} to {target} is not supported"))
    if start == target:  # already there: no-op, still a copy
        return MigrationResult(copy.deepcopy(blueprint), start, target, [], [])
    if meta.get("buildState") != "draft" and not allow_non_draft:
        return _fail(Issue("MIG-STATE-001", "/meta/buildState",
                           "only a draft is migrated by default; a frozen revision must not change silently (pass allow_non_draft)"))
    chain = reg.path(start, target)
    if isinstance(chain, Issue):
        return _fail(chain)
    doc = copy.deepcopy(blueprint)
    records = []
    for frm, to, fn in chain:
        before = copy.deepcopy(doc)
        try:
            out = fn(copy.deepcopy(doc))
        except Exception as exc:
            return _fail(Issue("MIG-STEP-001", "/", f"step {frm}->{to} raised {type(exc).__name__}"))
        if not isinstance(out, dict) or not isinstance(out.get("meta"), dict):
            return _fail(Issue("MIG-STEP-001", "/", f"step {frm}->{to} did not return a Blueprint object"))
        if out["meta"].get("schemaVersion") != frm:
            return _fail(Issue("MIG-STEP-003", "/meta/schemaVersion", f"step {frm}->{to} must leave schemaVersion to the framework"))
        for k in _PROTECTED:
            if out["meta"].get(k) != before["meta"].get(k) or (k in before["meta"]) != (k in out["meta"]):
                return _fail(Issue("MIG-STEP-002", f"/meta/{k}", f"step {frm}->{to} changed meta.{k}"))
        out["meta"]["schemaVersion"] = to
        records.append(StepRecord(frm, to, tuple(diff_changes(before, out))))
        doc = out
    if validate_result and target == CURRENT_SCHEMA_VERSION:
        try:
            from ._deps import validate
            rep = validate(doc)
        except Exception as exc:
            return _fail(Issue("MIG-VALID-001", "/", f"validator could not run ({type(exc).__name__})"))
        if not rep.ok:
            return _fail(*[Issue("MIG-VALID-001", i.path, f"{i.code}: {i.message}") for i in rep.errors])
    return MigrationResult(doc, start, target, records, [])
