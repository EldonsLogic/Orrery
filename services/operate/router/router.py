"""IntentRouter: rules first, an injected closed-set classifier second, a safety combiner last (OPR-002).

Invariants (tested):
- Mode never grants authority: the decision has no role, tool or permission field; the runtime allow-list is built
  from the verified caller's roles only (runtime.allowlist.resolve_allowlist) and takes no mode.
- act and change are reached only when the rules saw an explicit request (command, imperative or desire plus an
  action verb) and any configured classifier agrees. Any uncertainty, disagreement, mixed request, polite question,
  instruction-like prose or classifier failure resolves to `ask` with a clarifying question key.
- act and change always require a confirmation turn; an affirmative reply counts only against a host-set pending.
- Untrusted data (L3) is never read. The classifier sees the user turn only. Its output is decoded against a closed
  label set; no text from it reaches the decision. The decision holds enum values and reason codes only."""
from __future__ import annotations

import re
from typing import Optional

from .models import (ABSTAIN, MODE_RISK_FLOOR, PRIVILEGED, RISK_ORDER, SAFE_MODE, RouteContext, RouteDecision,
                     max_risk)
from .ports import ClassifierRequest, ModelClassifierPort, bucket, decode_label
from .rules import RuleResult, run_rules
from .text import MAX_CHARS, normalise

CLARIFY_MODE = "router.clarify.mode"          # "Do you want to look something up, or make a change?"
CLARIFY_CONFIRM = "router.clarify.confirm"    # "Should I go ahead and do this? Say yes to confirm."
_YES = re.compile(r"^(?:yes|yep|yeah|confirm|confirmed|go ahead|proceed|do it|ok|okay|sure|نعم|ايوه|تمام|اكد|اكيد|موافق|نفذ)$")
_NO = re.compile(r"^(?:no|nope|cancel|stop|never mind|لا|الغاء|وقف|لا شكرا)$")


class IntentRouter:
    def __init__(self, classifier: Optional[ModelClassifierPort] = None):
        self._clf = classifier

    # -- public -------------------------------------------------------------------------------------------------
    def route(self, turn: str, ctx: RouteContext = RouteContext(), data: tuple = (),
              risk_hint: Optional[str] = None) -> RouteDecision:
        codes = {"data_ignored"} if data else set()  # `data` is counted, never read
        hint = risk_hint
        if hint is not None and hint not in RISK_ORDER:
            codes.add("hint_invalid")
            hint = "R4"  # an unreadable hint fails closed to the highest class
        if isinstance(turn, str) and len(turn) > MAX_CHARS:
            # never route a prefix of a longer turn: the model would later see the rest
            codes.add("input_truncated")
            return RouteDecision(SAFE_MODE, "low", tuple(sorted(codes)), True, CLARIFY_MODE, False,
                                 max_risk(hint), data_items_ignored=len(data))
        pending = self._pending(turn, ctx, codes, hint, len(data))
        if pending is not None:
            return pending
        rr = run_rules(turn, ctx.entity_names, ctx.blueprint_live)
        codes |= set(rr.reasons)
        mode, conf, abstain, clarify, label = self._combine(rr, turn, ctx, codes)
        confirm = mode in PRIVILEGED
        if confirm:
            codes.add("needs_confirmation")
        own = max_risk(rr.risk if mode in PRIVILEGED else "R0", MODE_RISK_FLOOR[mode])
        risk = max_risk(hint, own)
        if RISK_ORDER.index(risk) > RISK_ORDER.index(own):
            codes.add("hint_raised_risk")
        return RouteDecision(mode, conf, tuple(sorted(codes)), abstain, clarify, confirm, risk, rr.command,
                             rr.mode, label, len(data))

    # -- internals ----------------------------------------------------------------------------------------------
    def _pending(self, turn, ctx, codes, hint, n_data):
        t = normalise(turn)
        yes, no = bool(_YES.match(t)), bool(_NO.match(t))
        if not (yes or no):
            return None
        if ctx.pending is None or ctx.pending.mode not in PRIVILEGED:
            if yes:
                codes |= {"confirmation_without_pending"}
                return RouteDecision(SAFE_MODE, "low", tuple(sorted(codes)), True, CLARIFY_MODE,
                                     risk_hint=max_risk(hint), data_items_ignored=n_data)
            return None
        pend = ctx.pending
        if yes and not (ctx.now is not None and ctx.now < pend.expires_at):
            codes.add("pending_expired")  # no clock or past expiry: the confirmation is void, ask again
            return RouteDecision(SAFE_MODE, "low", tuple(sorted(codes)), True, CLARIFY_CONFIRM, False,
                                 max_risk(hint), data_items_ignored=n_data)
        codes.add("confirmation_of_pending")
        mode = pend.mode if yes else SAFE_MODE
        # the confirming decision carries the pending action's own risk and ids; it is advisory (see the doc)
        risk = max_risk(hint, MODE_RISK_FLOOR[mode], pend.risk if yes else None)
        return RouteDecision(mode, "high", tuple(sorted(codes)), False, None, False, risk, False, None, None,
                             n_data, confirms_action_id=pend.action_id if yes else None,
                             confirms_args_hash=pend.args_hash if yes else None,
                             extra={"confirms_pending": yes})

    def _classify(self, turn, ctx, codes):
        """Return (label or None, confidence). Never raises; never returns provider text."""
        if self._clf is None:
            codes.add("classifier_none")
            return None, 0.0
        try:
            raw = self._clf.classify(ClassifierRequest(normalise(turn), ctx.locale))
        except Exception:  # noqa: BLE001  fail closed: the exception text is dropped
            codes.add("classifier_error")
            return None, 0.0
        label, conf = decode_label(raw)
        if label is None:
            codes.add("classifier_invalid")
        elif label == ABSTAIN:
            codes.add("classifier_abstain")
        return (label if label != ABSTAIN else None), conf

    def _combine(self, rr: RuleResult, turn, ctx, codes):
        """Return (mode, confidence, abstain, clarify_key, classifier_label)."""
        def safe(clarify=CLARIFY_MODE, abstain=True, label=None):
            return SAFE_MODE, "low", abstain, clarify if abstain else None, label

        mode = rr.mode
        if rr.meta and (mode in PRIVILEGED or mode is None):
            return safe()
        if "ambiguous_reference" in rr.reasons:
            return safe()  # which record? Always ask, whatever the classifier says
        if mode in PRIVILEGED and rr.command:
            return self._availability(mode, "high", ctx, codes) or safe()
        if mode is None:
            if rr.polite:
                return safe(CLARIFY_CONFIRM)
            if "mixed_intent" in rr.reasons:
                return safe()
            label, conf = self._classify(turn, ctx, codes)
            rescue_ok = ("ask",) if ctx.blueprint_live else ("ask", "discover")  # live: never discover by model alone
            if label in rescue_ok and conf >= 0.5 and "classifier_none" not in codes:
                codes.add("classifier_rescue")
                return label, min(bucket(conf), "medium", key=("low", "medium", "high").index), False, None, label
            if label in PRIVILEGED:
                codes.add("privileged_needs_rules")
            codes.add("no_signal")
            return safe(label=label)
        if mode in ("ask", "discover") and rr.confidence == "high":
            return mode, "high", False, None, None
        label, conf = self._classify(turn, ctx, codes)
        if mode in PRIVILEGED:
            if label == mode and conf >= 0.5 and (rr.confidence == "high" or conf >= 0.8):
                codes.add("classifier_agree")
                return self._availability(mode, "high", ctx, codes) or safe(label=label)
            if self._clf is None and rr.confidence == "high":
                return self._availability(mode, "high", ctx, codes) or safe()
            if label is not None and label != mode:
                codes.add("classifier_disagree")
            return safe(label=label)
        # rules say ask or discover with medium confidence
        if self._clf is None or label == mode:
            if label == mode:
                codes.add("classifier_agree")
            return mode, rr.confidence, False, None, label
        if label is not None:
            codes.add("classifier_disagree")
        return safe(label=label)

    def _availability(self, mode, conf, ctx, codes):
        """Before go-live there is no Tool API: act is unavailable and change is Blueprint building (discover)."""
        if ctx.blueprint_live:
            return mode, conf, False, None, None
        if mode == "change":
            codes.add("pre_live_change_is_discovery")
            return "discover", conf, False, None, None
        codes.add("act_unavailable")
        return None
