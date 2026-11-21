"""Deterministic fake of the model-call contract (contracts/model-call.md 0.1.0, PLT-026) for tests.

Eldon-lane callers build against this until the real gateway (services/gateway/, PLT-009) implements the contract.
It makes no network call and reads no key. Requests and replies are plain dicts in the contract's JSON shape;
a refusal is raised as `ModelCallRefused` and also has the contract's JSON shape (`.as_dict()`)."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field

CONTRACT_VERSION = "0.1.0"
TIERS = ("small", "mid", "frontier")                    # weakest to strongest
PURPOSES = frozenset({"chat", "agent", "build", "simulation"})
TRUST_ORDER = ("platform", "tenant_config", "user", "untrusted")
DATA_CLASSES = ("C0", "C1", "C2", "C3")
RETRYABLE = frozenset({"model_unavailable"})
FORBIDDEN_FIELDS = frozenset({"model", "model_id", "provider", "endpoint", "api_key", "authorization"})
MAX_ATTEMPTS = 3
CHARS_PER_TOKEN = 3
FIXED_TS = "2026-01-01T00:00:00.000Z"  # deterministic meter timestamps
# micro-USD per 1M tokens (input, output): the PLT-025 default tier rates, UNVERIFIED
DEFAULT_RATES = {"frontier": (5_000_000, 25_000_000), "mid": (3_000_000, 15_000_000), "small": (800_000, 4_000_000)}
# Test-only secret shapes (a subset of scripts/scan_secrets.py); the real filter is the gateway's S23 feed.
_SECRET = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY|\b(?:AKIA|ASIA)[0-9A-Z]{16}\b|\bsk-[A-Za-z0-9_-]{20,}")


class ModelCallRefused(Exception):
    def __init__(self, call_id: str, code: str, reason: str):
        super().__init__(f"{code}:{reason}")
        self.call_id, self.code, self.reason, self.retryable = call_id, code, reason, code in RETRYABLE

    def as_dict(self) -> dict:
        return {"kind": "refusal", "call_id": self.call_id, "code": self.code, "reason": self.reason,
                "retryable": self.retryable, "reservation_released": True}


@dataclass(frozen=True)
class Entry:
    """One routing-table entry. `name` stands in for the model id (internal only)."""
    name: str
    tier: str
    region_ok: bool = True


@dataclass
class Reservation:
    id: str
    call_id: str
    entry: str
    amount: int
    state: str = "reserved"   # reserved -> committed | released, exactly once
    committed: int = 0


@dataclass
class FakeModelCallPort:
    """`session` is the verified caller (contract `caller`) of the service session this port is bound to.
    `budgets` maps layer -> cap in micro-USD; a layer listed in `layers` with no cap is `policy_missing`.
    `kill_switch` None means the flag is unreachable. `region_max_class` None means no region policy."""
    session: dict
    budgets: dict = field(default_factory=lambda: {"tenant": 1_000_000, "session": 100_000, "run": 50_000})
    layers: tuple = ("tenant", "session", "run")
    meter_up: bool = True
    kill_switch: object = False
    region_max_class: object = "C3"
    filter_up: bool = True
    chains: dict = field(default_factory=lambda: {t: [Entry(f"{t}-primary", t), Entry(f"{t}-secondary", t)]
                                                  for t in TIERS})
    down: set = field(default_factory=set)               # entry names whose transport fails
    reply_text: object = None                            # str, or callable(request) -> str
    rates: dict = field(default_factory=lambda: dict(DEFAULT_RATES))

    def __post_init__(self):
        self.spent = {k: 0 for k in self.layers}
        self.reservations: list = []
        self.events: list = []
        self.attempt_log: list = []
        self._idem: dict = {}

    # -- public -----------------------------------------------------------------------------------------------------
    def complete(self, request: dict) -> dict:
        call_id = str(request.get("call_id") or "unknown")[:128] if isinstance(request, dict) else "unknown"
        self._validate(call_id, request)
        key, digest = request["idempotency_key"], _digest(request)
        if key in self._idem:
            prev_digest, prev = self._idem[key]
            if prev_digest != digest:
                raise ModelCallRefused(call_id, "invalid_request", "idempotency_conflict")
            return dict(prev, replayed=True)
        self._gate(call_id, request)
        reply = self._dispatch(call_id, request)
        self._idem[key] = (digest, reply)
        return reply

    # -- checks before any reservation ------------------------------------------------------------------------------
    def _validate(self, call_id, r):
        bad = lambda reason: ModelCallRefused(call_id, "invalid_request", reason)  # noqa: E731
        if not isinstance(r, dict) or r.get("kind") != "request" or r.get("contract_version") != CONTRACT_VERSION:
            raise bad("schema")
        if FORBIDDEN_FIELDS & set(r):
            raise bad("model_named")
        if r.get("caller") != self.session:
            raise bad("caller_mismatch")
        if any(re.match(r"(?i)^tenant", k) for k in (r.get("metadata") or {})):
            raise bad("tenant_in_payload")
        if r.get("tier") not in TIERS or r.get("purpose") not in PURPOSES or not r.get("prompt_version"):
            raise bad("schema")
        if not isinstance(r.get("idempotency_key"), str) or not 8 <= len(r["idempotency_key"]) <= 128:
            raise bad("schema")
        if not isinstance(r.get("accepts_untrusted"), bool):
            raise bad("schema")
        mx, mn = r.get("max_output_tokens"), r.get("min_output_tokens", r.get("max_output_tokens"))
        if not (_int(mx) and _int(mn) and 1 <= mn <= mx <= 32000):
            raise bad("limit")
        blocks = r.get("blocks")
        if not isinstance(blocks, list) or not blocks:
            raise bad("schema")
        last = 0
        for b in blocks:
            if not isinstance(b, dict) or b.get("trust") not in TRUST_ORDER:
                raise bad("missing_trust_label")
            if b.get("data_class") not in DATA_CLASSES or not isinstance(b.get("text"), str):
                raise bad("schema")
            if b["trust"] == "untrusted" and not b.get("source"):
                raise bad("schema")
            rank = TRUST_ORDER.index(b["trust"])
            if rank < last:
                raise bad("block_order")
            last = rank

    def _gate(self, call_id, r):
        if self.kill_switch is None:
            raise ModelCallRefused(call_id, "kill_switch_engaged", "unreachable")
        if self.kill_switch:
            raise ModelCallRefused(call_id, "kill_switch_engaged", "engaged")
        if self.region_max_class is None:
            raise ModelCallRefused(call_id, "region_policy_refused", "policy_missing")
        top = DATA_CLASSES.index(self.region_max_class)
        if any(DATA_CLASSES.index(b["data_class"]) > top for b in r["blocks"]):
            raise ModelCallRefused(call_id, "region_policy_refused", "data_class_not_allowed")
        if not r["accepts_untrusted"] and any(b["trust"] == "untrusted" for b in r["blocks"]):
            raise ModelCallRefused(call_id, "injection_tainted", "untrusted_not_accepted")
        if not self.filter_up:
            raise ModelCallRefused(call_id, "filter_blocked", "filter_unavailable")
        if any(_SECRET.search(b["text"]) for b in r["blocks"]):
            raise ModelCallRefused(call_id, "filter_blocked", "secret_in_prompt")
        if not self.meter_up:
            raise ModelCallRefused(call_id, "budget_refused", "meter_unavailable")
        if any(self.budgets.get(k) is None for k in self.layers):
            raise ModelCallRefused(call_id, "budget_refused", "policy_missing")

    # -- reservation, fallback, commit ------------------------------------------------------------------------------
    def _chain(self, tier):
        rank = TIERS.index(tier)
        return [e for t in TIERS[rank:] for e in self.chains.get(t, []) if e.region_ok][:MAX_ATTEMPTS]

    def _cost(self, tier, inp, out):
        ri, ro = self.rates[tier]
        return -(-(inp * ri + out * ro) // 1_000_000)

    def _remaining(self):
        held = sum(x.amount for x in self.reservations if x.state == "reserved")
        return min(self.budgets[k] - self.spent[k] for k in self.layers) - held

    def _reserve(self, call_id, entry, r, est_in):
        mx, mn = r["max_output_tokens"], r.get("min_output_tokens", r["max_output_tokens"])
        ri, ro = self.rates[entry.tier]
        limit = min(mx, (self._remaining() * 1_000_000 - est_in * ri) // ro)  # largest affordable output
        if limit < mn:
            raise ModelCallRefused(call_id, "budget_refused", "exceeded")
        res = Reservation(f"rsv_{len(self.reservations) + 1}", call_id, entry.name,
                          self._cost(entry.tier, est_in, limit))
        self.reservations.append(res)
        return res, limit

    def _dispatch(self, call_id, r):
        est_in = -(-sum(len(b["text"]) for b in r["blocks"]) // CHARS_PER_TOKEN)
        chain = self._chain(r["tier"])
        if not chain:
            raise ModelCallRefused(call_id, "region_policy_refused", "no_allowed_endpoint")
        for attempt, entry in enumerate(chain, 1):
            res, limit = self._reserve(call_id, entry, r, est_in)
            self.attempt_log.append((call_id, entry.name, "ok" if entry.name not in self.down else "transport"))
            if entry.name in self.down:
                res.state = "released"                    # transport failure: release, fall back
                continue
            text = self.reply_text(r) if callable(self.reply_text) else self.reply_text
            text = text if isinstance(text, str) else "fake:" + _digest(r)[:16]
            if _SECRET.search(text):
                res.state = "released"
                raise ModelCallRefused(call_id, "filter_blocked", "secret_in_output")
            wanted = max(1, -(-len(text) // CHARS_PER_TOKEN))
            out = min(limit, wanted)
            cost = self._cost(entry.tier, est_in, out)
            res.state, res.committed = "committed", cost
            for k in self.layers:
                self.spent[k] += cost
            event_id = "01HZZZZZZZZZZZZZZZZZ" + f"{len(self.events) + 1:06d}"
            self.events.append(self._meter_event(event_id, r, entry, est_in, out, cost))
            return {"kind": "reply", "call_id": call_id, "idempotency_key": r["idempotency_key"],
                    "tier": entry.tier, "text": text, "tool_calls": [],
                    "stop_reason": "max_output" if wanted > limit else "end",
                    "trust": "untrusted", "tainted": any(b["trust"] == "untrusted" for b in r["blocks"]),
                    "usage": {"input_tokens": est_in, "output_tokens": out, "cached_tokens": 0,
                              "cost_micro_usd": cost},
                    "attempts": attempt, "fallback_used": attempt > 1, "meter_event_id": event_id,
                    "model_id": entry.name, "replayed": False}
        raise ModelCallRefused(call_id, "model_unavailable", "chain_exhausted")

    def _meter_event(self, event_id, r, entry, inp, out, cost):
        c = r["caller"]
        return {"event_id": event_id, "type": "meter.ai_usage", "schema_version": 1, "occurred_at": FIXED_TS,
                "recorded_at": FIXED_TS, "tenant_id": c["tenant_id"],
                "actor": {"kind": c["actor_kind"], "id": c["actor_id"], "role_ids": list(c["role_ids"]),
                          "on_behalf_of": c.get("on_behalf_of")},
                "source": {"service": "gateway"}, "correlation_id": c["correlation_id"], "causation_id": None,
                "subject": None, "data_class": "operational",
                "data": {"model_id": entry.name, "tier": entry.tier, "input_tokens": inp, "output_tokens": out,
                         "cached_tokens": 0, "cost_micro_usd": cost, "purpose": r["purpose"],
                         "agent_id": c.get("agent_id")},
                "trace": {"model_id": entry.name, "prompt_version": r["prompt_version"]}}


def _int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _digest(r: dict) -> str:
    return hashlib.sha256(json.dumps(r, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
