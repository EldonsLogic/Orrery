"""Injected ports. build_state imports nothing from services/control-plane or the engine (Q-432): the host wires
thin adapters. All are duck-typed; the machine validates every answer strictly and treats anything unexpected as a
refusal.

Identity: `resolve(claims, *, step_up: bool) -> Principal`. Claim assumptions (ADR-0047, ADR-0048; the host adapter
over the identity service must guarantee them, the machine cannot):
- `claims` are the verified, live claims of the calling session (token live, session version current), never a value
  from a request body.
- `kind` is "human" only for an interactive human session. Agent tokens (ADR-0048) and service accounts are "agent"
  and "service"; they can never pass a gate.
- When `step_up` is true the adapter consumes one fresh MFA step-up (ADR-0047; one decision per step-up) and raises
  if there is none; it sets `Principal.step_up` True only then. The machine requires both.
- `realm` and `tenant_id`: an owner is a tenant-realm principal bound to exactly one tenant; a team reviewer is a
  staff-realm principal (tenant_id None); `roles` come from the identity service's role resolver for that principal.

Blueprints: `load(tenant_id, blueprint_id) -> dict`, the content from the host's own store (never from the caller).
Validator: `(content) -> list` of error codes; empty means valid (services/blueprint validator).
Reviews: `verify(tenant_id, item_id, content, pinned_seq, pinned_head) -> dict`, a thin adapter over the PLT-013
`ReviewQueue.verify_evidence` using the `evidence_reader` service principal (Q-490).
Simulations: `load(tenant_id, simulation_id) -> dict`, the BPL-018 report from the host's own store.
Engine: `apply(tenant_id, kind, idempotency_key, content_digest) -> "confirmed" | "failed" | "unknown"` and
`status(tenant_id, idempotency_key) -> same`, a thin adapter over the engine-adapter contract (idempotent by key);
`kind` is "sandbox" or "live". The machine never names or reaches the engine itself.
Owner approvals: `verify(tenant_id, blueprint_id, content_digest, quote_digest, subject) -> dict` with exactly the keys tenantId,
blueprintId, contentDigest, quoteDigest (echoes), approvedBy (`subject` when that owner's sealed approval covers this
digest and quote, else None), blocked (a rejection, request for changes or hold) and quoteCurrent (the quote is still the
live one); a thin adapter over services/discovery/owner_approval (DSC-009, ADR-0050 amendment). Never trusted from a caller.
Clock: `() -> int`, whole epoch seconds from the host clock (never the caller's).
"""
from __future__ import annotations

from dataclasses import dataclass

KINDS = ("human", "agent", "service")
REALMS = ("tenant", "staff")
OWNER, REVIEWER, RUNNER = "owner", "team_reviewer", "build_runner"
ROLE_REALM = {OWNER: "tenant", REVIEWER: "staff", RUNNER: "staff"}


@dataclass(frozen=True)
class Principal:
    subject: str
    kind: str
    realm: str
    tenant_id: object  # str for a tenant-realm principal, None for staff
    roles: tuple
    step_up: bool
