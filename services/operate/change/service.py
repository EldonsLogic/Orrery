"""ChangeService (OPR-009): a `change` request becomes a Blueprint change proposal, previewed, then applied only after
the confirmation bound to that exact proposal, through the existing Blueprint path.

Invariants (tested):
- The model only drafts typed edits (`edits.py`). Code applies them to a copy, the validator and the schema decide
  validity, `bpdiff` computes the diff, and `policy.check_diff` decides on EVERY changed path of that diff (default
  deny, explicit low-risk allow-list; owning entity of entity, workflow, report and label-override ops; tax and money
  fields). Risk comes from the diff's impact classes, the entity class and the router's hint (never lowered). Changes
  above R2 are refused here and go through Studio review (ADR-0027).
- A proposal digest binds tenant, user, session, base hash, target hash, diff hash, risk and expiry. The host sets the
  router's `Pending` from `pending_for(proposal)`; a confirming decision must carry the same action id and digest
  (Q-265). On confirm the service re-derives the target from the stored edits and the live Blueprint and re-checks
  everything; any difference refuses. A proposal is used once (compare-and-delete before the apply call), expires, and
  a newer proposal in the same session supersedes the older one, even mid-confirm. Untrusted data (L3) is never read.
- The port runs the apply under the caller's identity (`actor`). Only a typed `ApplyRefused` means "nothing changed";
  any other failure is resolved by idempotency key or reported as `change_outcome_unknown`. Confirm refusals are
  audited.
- The only write is `BlueprintPort.submit_change`; the engine is never touched here. Every failure fails closed with a
  code from `errors.py`; nothing from the model or an exception reaches the customer."""
from __future__ import annotations

import copy
import hashlib
import json
import logging
import math
from typing import Callable, Optional

from router.models import RISK_ORDER, MODE_RISK_FLOOR, Pending, RouteDecision, max_risk

from . import edits as ed
from . import policy
from ._deps import bpdiff, blueprint_hash, validate
from .errors import ChangeRefused
from .models import (ACTION_ID, DEFAULT_TTL_S, IMPACT_RISK, MAX_CHAT_RISK, ApplyRefused, BlueprintPort,
                     ChangeDrafterPort, DraftRequest, Outcome, Preview, Proposal)
from .store import InMemoryProposalStore

log = logging.getLogger("change")
_RANK = {r: i for i, r in enumerate(RISK_ORDER)}


def _canon(v) -> bytes:
    return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _sha(v) -> str:
    return "sha256:" + hashlib.sha256(_canon(v)).hexdigest()


def digest_of(tenant_id, user_id, session_id, base_hash, target_hash, diff_hash, risk, expires_at) -> str:
    return _sha({"v": 1, "action": ACTION_ID, "tenant": tenant_id, "user": user_id, "session": session_id,
                 "base": base_hash, "target": target_hash, "diff": diff_hash, "risk": risk, "expires": expires_at})


def _outline(bp: dict) -> dict:
    """Ids only: no label text, so nothing a tenant typed reaches the drafter as instructions."""
    def ids(items):
        return [x["id"] for x in items if isinstance(x, dict) and isinstance(x.get("id"), str)]
    ents = {}
    for e in bp.get("entities") or []:
        if isinstance(e, dict) and isinstance(e.get("id"), str):
            ents[e["id"]] = ids(e.get("fields") or [])
    return {"entities": ents, "workflows": ids(bp.get("workflows") or []), "reports": ids(bp.get("reports") or []),
            "locales": list((bp.get("meta") or {}).get("locales") or [])}


def _clock_ok(now) -> bool:
    return type(now) in (int, float) and math.isfinite(now)


class ChangeService:
    def __init__(self, *, blueprints: BlueprintPort, drafter: ChangeDrafterPort, clock: Callable[[], float],
                 allowed_roles, store=None, audit: Optional[Callable[[dict], None]] = None,
                 ttl_s: float = DEFAULT_TTL_S):
        if type(ttl_s) not in (int, float) or not math.isfinite(ttl_s) or ttl_s <= 0:
            raise ChangeRefused("change_unavailable")
        self.bp, self.drafter, self.clock = blueprints, drafter, clock
        self.allowed_roles = frozenset(allowed_roles)  # required: no default role may change the configuration
        self.store = store or InMemoryProposalStore()
        self.audit, self.ttl_s = audit, ttl_s

    # ---- helpers -------------------------------------------------------------------------------------------
    def _emit(self, kind: str, p, **extra) -> None:
        if self.audit is None:
            return
        try:  # hashes and codes only; never the turn, the edits' values or the model output
            self.audit({"kind": kind, "tenant": getattr(p, "tenant_id", None), "user": getattr(p, "subject", None),
                        **extra})
        except Exception:  # noqa: BLE001  an audit failure must not turn into a write
            log.warning("change audit failed")

    def _check_caller(self, principal) -> None:
        if not (getattr(principal, "tenant_id", "") and getattr(principal, "subject", "")
                and getattr(principal, "role_ids", ())):
            raise ChangeRefused("change_no_permission")
        if not self.allowed_roles & set(principal.role_ids):
            raise ChangeRefused("change_no_permission")

    def _validate_ok(self, blueprint, ctx, side_code: str) -> None:
        try:
            report = validate(copy.deepcopy(blueprint), ctx)
        except Exception:  # noqa: BLE001  a validator crash is a refusal, never a pass
            raise ChangeRefused(side_code) from None
        if not report.ok:
            raise ChangeRefused(side_code)

    def _derive(self, tenant_id, edit_list, current, ctx, hint_risk):
        """Deterministic part, shared by propose and confirm. Returns (target, diff, risk)."""
        ed.check_allowed(edit_list)  # early exit only; the binding check is on the diff below
        target = ed.apply_edits(current, edit_list)
        if blueprint_hash(target) == blueprint_hash(current):
            raise ChangeRefused("change_no_effect")
        self._validate_ok(target, ctx, "change_invalid_blueprint")
        try:
            d = bpdiff.diff(current, target)
        except Exception:  # noqa: BLE001
            raise ChangeRefused("change_invalid_blueprint") from None
        if d["base"]["hash"] != blueprint_hash(current) or d["target"]["hash"] != blueprint_hash(target) or not d["ops"]:
            raise ChangeRefused("change_invalid_blueprint")
        floor = policy.check_diff(d, current, target)  # every changed path, default deny
        impact_risk = max_risk(*[IMPACT_RISK.get(op["impact"], "R4") for op in d["ops"]])  # unknown impact -> R4
        risk = max_risk(MODE_RISK_FLOOR["change"], impact_risk, floor, hint_risk)
        if _RANK[risk] > _RANK[MAX_CHAT_RISK]:
            raise ChangeRefused("change_needs_review")
        return target, d, risk

    # ---- propose -------------------------------------------------------------------------------------------
    def propose(self, principal, session_id: str, turn: str, decision: RouteDecision, locale: str = "en",
                data: tuple = ()) -> Preview:
        """Draft, check and preview a change. `data` (untrusted L3) is never read. Writes nothing."""
        self._check_caller(principal)
        if not isinstance(decision, RouteDecision) or decision.mode != "change" or not decision.requires_confirmation:
            raise ChangeRefused("change_not_change_mode")
        if not isinstance(turn, str) or not turn.strip() or not session_id:
            raise ChangeRefused("change_draft_failed")
        tenant, user = principal.tenant_id, principal.subject
        try:
            current = self.bp.current(tenant)
            ctx = self.bp.validation_context(tenant)
        except Exception:  # noqa: BLE001
            raise ChangeRefused("change_unavailable") from None
        self._validate_ok(current, ctx, "change_base_invalid")
        try:
            raw = self.drafter.draft(DraftRequest(turn, locale, _outline(current)))
        except Exception:  # noqa: BLE001  the provider's text is dropped
            raise ChangeRefused("change_draft_failed") from None
        edit_list = ed.decode_draft(raw)
        target, d, risk = self._derive(tenant, edit_list, current, ctx, decision.risk_hint)
        now = self.clock()
        if not _clock_ok(now):
            raise ChangeRefused("change_unavailable")
        expires = now + self.ttl_s
        digest = digest_of(tenant, user, session_id, d["base"]["hash"], d["target"]["hash"], _sha(d), risk, expires)
        prop = Proposal(tenant, user, session_id, edit_list, d["base"]["hash"], d["target"]["hash"], _sha(d), d, risk,
                        digest, now, expires)
        self.store.put(prop)  # supersedes any earlier proposal of this session
        self._emit("change.proposed", principal, digest=digest, risk=risk, ops=len(d["ops"]))
        from .preview import build_preview
        return build_preview(prop, locale)

    def pending_for(self, proposal_or_preview) -> Pending:
        """The router `Pending` the host must set after showing the preview. Set by trusted host state only."""
        x = proposal_or_preview
        return Pending("change", x.action_id, x.digest, x.risk, x.expires_at)

    def cancel(self, principal, session_id: str) -> None:
        self._check_caller(principal)
        self.store.drop(principal.tenant_id, principal.subject, session_id)

    # ---- confirm -------------------------------------------------------------------------------------------
    def confirm(self, principal, session_id: str, decision: RouteDecision, locale: str = "en") -> Outcome:
        """Apply the active proposal if, and only if, `decision` is a confirmation bound to exactly that proposal.
        Every refusal is audited (`change.refused`, code and digest prefix only)."""
        try:
            return self._confirm(principal, session_id, decision, locale)
        except ChangeRefused as e:
            ah = getattr(decision, "confirms_args_hash", None)
            self._emit("change.refused", principal, code=e.code, session=session_id,
                       digest=ah[:23] if isinstance(ah, str) else None)
            raise

    def _confirm(self, principal, session_id, decision, locale) -> Outcome:
        self._check_caller(principal)
        tenant, user = principal.tenant_id, principal.subject
        aid, ah = getattr(decision, "confirms_action_id", None), getattr(decision, "confirms_args_hash", None)
        if not isinstance(decision, RouteDecision) or decision.mode != "change" or not aid or not ah:
            raise ChangeRefused("change_confirmation_mismatch")
        prop = self.store.active(tenant, user, session_id)
        if prop is None:
            raise ChangeRefused("change_replayed" if self.store.used(ah) else "change_no_pending")
        if aid != prop.action_id or ah != prop.digest:
            raise ChangeRefused("change_confirmation_mismatch")  # a changed or other proposal: the old yes is void
        if (prop.tenant_id, prop.user_id, prop.session_id) != (tenant, user, session_id):
            raise ChangeRefused("change_confirmation_mismatch")
        now = self.clock()
        if not _clock_ok(now):
            raise ChangeRefused("change_unavailable")
        if not now < prop.expires_at:
            self.store.drop(tenant, user, session_id)
            raise ChangeRefused("change_expired")
        if digest_of(tenant, user, session_id, prop.base_hash, prop.target_hash, prop.diff_hash, prop.risk,
                     prop.expires_at) != prop.digest or _sha(prop.diff) != prop.diff_hash:
            raise ChangeRefused("change_tampered")
        try:
            current = self.bp.current(tenant)
            ctx = self.bp.validation_context(tenant)
        except Exception:  # noqa: BLE001
            raise ChangeRefused("change_unavailable") from None
        if blueprint_hash(current) != prop.base_hash:
            self.store.drop(tenant, user, session_id)
            raise ChangeRefused("change_stale")
        self._validate_ok(current, ctx, "change_base_invalid")
        # re-derive from the stored edits and the live Blueprint: the same inputs must give the same diff and risk
        target, d, risk = self._derive(tenant, prop.edits, current, ctx, "R0")
        if _sha(d) != prop.diff_hash or d["target"]["hash"] != prop.target_hash or _RANK[risk] > _RANK[prop.risk]:
            raise ChangeRefused("change_tampered")
        if not self.store.consume(prop):  # used once, before the write: a failed apply needs a new proposal
            raise ChangeRefused("change_replayed")
        actor = {"tenant": tenant, "subject": user, "roles": sorted(principal.role_ids), "session": session_id}
        try:
            res = self.bp.submit_change(tenant, copy.deepcopy(d), prop.digest, prop.digest, actor=actor, risk=prop.risk)
        except ApplyRefused:  # the Blueprint path refused before any write: nothing changed
            self._emit("change.apply_failed", principal, digest=prop.digest)
            raise ChangeRefused("change_apply_failed") from None
        except Exception:  # noqa: BLE001  timeout, crash: the write may or may not have happened
            res = self._resolve_unknown(principal, tenant, prop)
        self._emit("change.applied", principal, digest=prop.digest, risk=prop.risk)
        from .preview import applied_text
        return Outcome("applied", prop.digest, res if isinstance(res, dict) else {}, applied_text(len(d["ops"]), locale))

    def _resolve_unknown(self, principal, tenant, prop) -> dict:
        """Ask the Blueprint path by idempotency key; never claim "nothing changed" unless it says so."""
        try:
            status = self.bp.change_status(tenant, prop.digest)
        except Exception:  # noqa: BLE001
            status = "unknown"
        if status == "applied":
            return {}
        if status == "not_applied":
            self._emit("change.apply_failed", principal, digest=prop.digest)
            raise ChangeRefused("change_apply_failed")
        self._emit("change.outcome_unknown", principal, digest=prop.digest)
        raise ChangeRefused("change_outcome_unknown")
