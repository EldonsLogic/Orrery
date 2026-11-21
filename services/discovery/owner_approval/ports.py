"""Injected ports. This package imports nothing from services/control-plane or the build state machine (Q-432); the
host wires thin adapters. All are duck-typed; every answer is validated strictly and anything unexpected refuses.

identity.resolve(claims, *, step_up: bool) -> Principal. Claim assumptions (ADR-0047, ADR-0048; the host adapter must
guarantee them, this package cannot):
- `claims` are the verified, live claims of the calling session (token live, session version current), never a value
  from a request body.
- `kind` is "human" only for an interactive human session; agent tokens (ADR-0048) and service accounts are "agent" and
  "service" and can never decide.
- When `step_up` is true the adapter consumes one fresh MFA step-up (ADR-0047) and raises when there is none; it sets
  `Principal.step_up` True only then. This package requires both.
- An owner is a tenant-realm principal bound to exactly one tenant; `roles` come from the identity service's role
  resolver. A staff principal (realm "staff") can never decide for an owner.
blueprints.load(tenant_id, blueprint_id) -> dict           the current content from the host store.
quotes.load(tenant_id, blueprint_id) -> dict               the current quote draft (DSC-008) from the host store.
gaps.load(tenant_id, blueprint_id) -> dict                 the gap report (DSC-006) the quote was made from.
holds.held(tenant_id, blueprint_id) -> bool                True when the draft is quarantined or on hold.
gate: status(tenant_id, blueprint_id) -> dict              the build state machine's `status` (state, contentDigest,
                                                            contentChanged);
      approve_owner(claims, *, tenant_id, blueprint_id, confirmations)
      roll_back(claims, *, tenant_id, blueprint_id, to_state, reason)
                                                            the machine's own gates. Each resolves identity and
                                                            consumes a step-up itself (Q-520).
content_digest(content) -> str                              the machine's content digest function (build_state).
clock() -> int                                              whole epoch seconds from the host clock.
"""
from __future__ import annotations

from dataclasses import dataclass

KINDS = ("human", "agent", "service")
REALMS = ("tenant", "staff")
OWNER = "owner"
# Roles that make an owner unfit to decide (Q-503 line: staff reviewers and runners are never the owner gate).
CONFLICT_ROLES = frozenset({"team_reviewer", "build_runner"})


@dataclass(frozen=True)
class Principal:
    subject: str
    kind: str
    realm: str
    tenant_id: object  # str for a tenant-realm principal, None for staff
    roles: tuple
    step_up: bool
