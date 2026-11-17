"""Checks of the Blueprint-to-engine mapping (contracts/engine-mapping.schema.json) against the Blueprint being
compiled. The mapping contributes no value to the artifact (steps are engine-neutral); it is a gate: a mapping that
does not fit the Blueprint, names unknown keys, or would understate ledger risk refuses the compile."""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from jsonschema import Draft202012Validator

from ._deps import CONTRACTS
from .components import touches_ledger_or_tax
from .result import Issue, ptr

UNVERIFIED_PREFIX = "UNVERIFIED"


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    schema = json.loads((CONTRACTS / "engine-mapping.schema.json").read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def check_mapping(mapping: Any, blueprint: dict, resolved: dict[str, dict], environment: str) -> list[Issue]:
    """Every issue that makes this mapping unusable for this Blueprint in this environment."""
    if not isinstance(mapping, dict):
        return [Issue("CMP-MAP-001", "", "engine mapping must be a JSON object")]
    schema_issues = [Issue("CMP-MAP-001", ptr(*e.absolute_path), f"mapping schema: {e.validator} failed")
                     for e in _validator().iter_errors(mapping)]
    if schema_issues:  # shape unknown: the cross-checks below would guess
        return schema_issues
    issues: list[Issue] = []
    meta = blueprint["meta"]
    target = meta.get("engineTarget") or {}
    engine = mapping["engine"]
    if engine["adapter"] != target.get("adapter"):
        issues.append(Issue("CMP-MAP-003", "/engine/adapter",
                            f"mapping adapter '{engine['adapter']}' differs from the Blueprint's '{target.get('adapter')}'"))
    vs = engine["versionSet"]
    if vs != target.get("versionSet") and not (mapping["status"] == "draft" and vs.startswith(UNVERIFIED_PREFIX)):
        issues.append(Issue("CMP-MAP-003", "/engine/versionSet",
                            f"mapping version set differs from the Blueprint's '{target.get('versionSet')}'"))
    if mapping["blueprintRef"]["contract"] != meta.get("schemaVersion"):
        issues.append(Issue("CMP-MAP-004", "/blueprintRef/contract",
                            f"mapping targets Blueprint contract '{mapping['blueprintRef']['contract']}', "
                            f"the Blueprint is '{meta.get('schemaVersion')}'"))
    if environment == "production" and mapping["status"] != "verified":
        issues.append(Issue("CMP-MAP-005", "/status", "a mapping that is not 'verified' cannot compile for production"))
    issues += _check_refs(mapping, blueprint)
    issues += _check_grants(mapping, blueprint)
    issues += _check_ledger(mapping, blueprint, resolved)
    issues += _check_rounding(mapping, blueprint)
    return issues


def _index(blueprint: dict) -> tuple[dict, dict]:
    entities = {e["id"]: e for e in blueprint.get("entities", [])}
    roles = {r["id"]: r for r in blueprint.get("roles", [])}
    return entities, roles


def _fields(entity: dict) -> dict:
    return {f["id"]: f for f in entity.get("fields", [])}


def _check_refs(mapping: dict, blueprint: dict) -> list[Issue]:
    entities, roles = _index(blueprint)
    out: list[Issue] = []

    def need_entity(name: str, where: str) -> dict | None:
        if name not in entities:
            out.append(Issue("CMP-MAP-002", where, f"entity '{name}' is not in the Blueprint"))
            return None
        return entities[name]

    for i, em in enumerate(mapping["entities"]):
        e = need_entity(em["blueprintEntity"], ptr("entities", i, "blueprintEntity"))
        if e is None:
            continue
        fields = _fields(e)
        for j, fm in enumerate(em["fields"]):
            f = fields.get(fm["blueprintField"])
            where = ptr("entities", i, "fields", j)
            if f is None:
                out.append(Issue("CMP-MAP-002", where, f"field '{e['id']}.{fm['blueprintField']}' is not in the Blueprint"))
            elif f.get("type") != fm["blueprintType"]:
                out.append(Issue("CMP-MAP-002", where + "/blueprintType",
                                 f"'{e['id']}.{f['id']}' is '{f.get('type')}' in the Blueprint, not '{fm['blueprintType']}'"))
        parent = em.get("parent")
        if parent:
            pe = need_entity(parent["blueprintEntity"], ptr("entities", i, "parent", "blueprintEntity"))
            rels = {r["id"]: r for r in (pe or {}).get("relations", [])}
            rel = rels.get(parent["relation"])
            if pe is not None and (rel is None or rel.get("target") != e["id"]):
                out.append(Issue("CMP-MAP-002", ptr("entities", i, "parent", "relation"),
                                 f"'{pe['id']}' has no relation '{parent['relation']}' to '{e['id']}'"))
    for i, rm in enumerate(mapping["roles"]):
        if rm["blueprintRole"] not in roles:
            out.append(Issue("CMP-MAP-002", ptr("roles", i, "blueprintRole"), f"role '{rm['blueprintRole']}' is not in the Blueprint"))
        for j, g in enumerate(rm["grants"]):
            e = need_entity(g["blueprintEntity"], ptr("roles", i, "grants", j, "blueprintEntity"))
            for k, mask in enumerate(g.get("fieldMasks", [])):
                if e is not None and mask["blueprintField"] not in _fields(e):
                    out.append(Issue("CMP-MAP-002", ptr("roles", i, "grants", j, "fieldMasks", k),
                                     f"field '{e['id']}.{mask['blueprintField']}' is not in the Blueprint"))
    for i, op in enumerate(mapping["operations"]):
        for key in ("fromEntity", "toEntity"):
            if key in op:
                need_entity(op[key], ptr("operations", i, key))
    for i, u in enumerate(mapping.get("unmapped", [])):
        e = need_entity(u["blueprintEntity"], ptr("unmapped", i, "blueprintEntity"))
        if e is not None and u["blueprintField"] not in _fields(e):
            out.append(Issue("CMP-MAP-002", ptr("unmapped", i, "blueprintField"),
                             f"field '{e['id']}.{u['blueprintField']}' is not in the Blueprint"))
    return out


def _check_grants(mapping: dict, blueprint: dict) -> list[Issue]:
    """A grant may not exceed what the Blueprint role allows on that entity (engine-mapping.md, Roles)."""
    _, roles = _index(blueprint)
    out = []
    for i, rm in enumerate(mapping["roles"]):
        role = roles.get(rm["blueprintRole"])
        if role is None:
            continue
        allowed = {p["entity"]: set(p.get("actions", [])) for p in role.get("permissions", [])}
        for j, g in enumerate(rm["grants"]):
            extra = sorted(set(g["actions"]) - allowed.get(g["blueprintEntity"], set()))
            if extra:
                out.append(Issue("CMP-MAP-006", ptr("roles", i, "grants", j, "actions"),
                                 f"grant exceeds Blueprint role '{role['id']}' on '{g['blueprintEntity']}': {', '.join(extra)}"))
    return out


def _check_ledger(mapping: dict, blueprint: dict, resolved: dict[str, dict]) -> list[Issue]:
    """An entity the mapping says posts stock or ledger entries must be bound to a ledger or tax component, so the
    artifact's touchesLedgerOrTax (and with it the team review) cannot be understated."""
    entities, _ = _index(blueprint)
    out = []
    for i, em in enumerate(mapping["entities"]):
        e = entities.get(em["blueprintEntity"])
        if e is None or em["ledgerEffect"] == "none":
            continue
        bound = [resolved.get(b["component"]) for b in e.get("components", [])]
        if not any(m is not None and touches_ledger_or_tax(m) for m in bound):
            out.append(Issue("CMP-MAP-007", ptr("entities", i, "ledgerEffect"),
                             f"'{e['id']}' has ledger effect '{em['ledgerEffect']}' but no bound ledger or tax component"))
    return out


def _check_rounding(mapping: dict, blueprint: dict) -> list[Issue]:
    """The engine computes and rounds (ADR-0030, ADR-0033); the compiler only checks that the mapping's stated
    precision agrees with the Blueprint field's precision. No value is computed or chosen here."""
    entities, _ = _index(blueprint)
    out = []
    for i, em in enumerate(mapping["entities"]):
        fields = _fields(entities.get(em["blueprintEntity"], {}))
        for j, fm in enumerate(em["fields"]):
            comp, f = fm.get("computed"), fields.get(fm["blueprintField"])
            if not comp or f is None or "precision" not in f:
                continue
            if comp["rounding"]["precision"] != f["precision"]:
                out.append(Issue("CMP-MAP-008", ptr("entities", i, "fields", j, "computed", "rounding", "precision"),
                                 f"mapping precision {comp['rounding']['precision']} differs from the Blueprint's "
                                 f"{f['precision']} for '{em['blueprintEntity']}.{f['id']}'"))
    return out
