"""Deterministic fake of the model-call contract (contracts/model-call.md 0.2.1, PLT-026) for tests.

Eldon-lane callers build against this until the real gateway (services/gateway/, PLT-009) implements the contract.
It makes no network call and reads no key. Requests and replies are plain dicts in the contract's JSON shape;
a refusal is raised as `ModelCallRefused` and also has the contract's JSON shape (`.as_dict()`).
Every request is validated against contracts/model-call.schema.json first (needs `jsonschema`; fails closed)."""
from __future__ import annotations

import functools
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

CONTRACT_VERSION = "0.2.1"
SCHEMA_PATH = Path(__file__).resolve().parents[3] / "contracts" / "model-call.schema.json"
TIERS = ("small", "mid", "frontier")                    # weakest to strongest
TRUST_ORDER = ("platform", "tenant_config", "user", "untrusted")
REF_TRUST = ("platform", "tenant_config")
DATA_CLASSES = ("C0", "C1", "C2", "C3")
RETRYABLE = frozenset({"model_unavailable"})
FORBIDDEN_FIELDS = frozenset({"model", "model_id", "provider", "endpoint", "api_key", "authorization"})
IDENTITY_FIELDS = ("tenant_id", "actor_kind", "actor_id", "session_id", "on_behalf_of", "agent_id", "run_id",
                   "thread_id")
LAYER_ID = {"tenant": "tenant_id", "session": "session_id", "agent": "agent_id", "run": "run_id"}
ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
MAX_REQUEST_BYTES = 1_048_576
MAX_ATTEMPTS = 3
FRAMING_TOKENS = 16      # per block and per tool: provider message framing allowance on top of the UTF-8 byte bound
FIXED_TS = "2026-01-01T00:00:00.000Z"  # deterministic meter timestamps
# micro-USD per 1M tokens (input, output): the PLT-025 default tier rates, UNVERIFIED
DEFAULT_RATES = {"frontier": (5_000_000, 25_000_000), "mid": (3_000_000, 15_000_000), "small": (800_000, 4_000_000)}
# Test-only secret shapes (a subset of scripts/scan_secrets.py); the real filter is the gateway's S23 feed.
_SECRET = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY|(?:AKIA|ASIA)[0-9A-Z]{16}|sk-[A-Za-z0-9_-]{20,}")


def content_hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canon(doc) -> str:
    return json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def tool_hash(spec: dict) -> str:
    return content_hash(_canon(spec))


@functools.lru_cache(maxsize=1)
def _validator():
    try:
        from jsonschema import Draft202012Validator
    except ImportError as exc:  # fail closed: the fake never accepts an unvalidated request
        raise RuntimeError("model_call_fake needs jsonschema (services/blueprint/requirements.txt)") from exc
    return Draft202012Validator(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))


class ModelCallRefused(Exception):
    def __init__(self, call_id, code: str, reason: str, reservation_released: bool = True):
        super().__init__(f"{code}:{reason}")
        self.call_id, self.code, self.reason = call_id, code, reason
        self.retryable, self.reservation_released = code in RETRYABLE, reservation_released

    def as_dict(self) -> dict:
        return {"kind": "refusal", "call_id": self.call_id, "code": self.code, "reason": self.reason,
                "retryable": self.retryable, "reservation_released": self.reservation_released}


@dataclass(frozen=True)
class Entry:
    """One routing-table entry. `name` stands in for the model id (internal only: trace and meter)."""
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


def _empty_registry():
    return {"platform": {}, "tenant_config": {}, "tools": {}, "applied_revision": {}}


@dataclass
class FakeModelCallPort:
    """`principal` is the verified identity of the service session (service, tenant, actor, roles, session) plus,
    for agent runs, `agent_id` and `run_id` from the signed run token. The body `caller` is only compared with it.
    `registry`: platform {(prompt_version, content_id): {text, data_class}}, tenant_config {(tenant, revision,
    content_id): {...}}, tools {(prompt_version, name): spec}, applied_revision {tenant: revision}.
    `budgets` maps layer -> cap in micro-USD; a layer in `layers` with no cap is `policy_missing`, with no id in the
    principal `layer_unbound`. `kill_switch` None means unreachable. `region_max_class` None means no policy.
    `down`: entries failing before the provider got the request; `timeouts`: entries timing out after send.
    `idem_store` may be shared between ports to test namespacing."""
    principal: dict
    registry: dict = field(default_factory=_empty_registry)
    budgets: dict = field(default_factory=lambda: {"tenant": 1_000_000, "session": 100_000, "run": 50_000})
    layers: tuple = ("tenant", "session", "run")
    meter_up: bool = True
    kill_switch: object = False
    region_max_class: object = "C3"
    filter_up: bool = True
    extra_fingerprints: set = field(default_factory=set)  # stands in for S23 keyed fingerprints
    chains: dict = field(default_factory=lambda: {t: [Entry(f"{t}-primary", t), Entry(f"{t}-secondary", t)]
                                                  for t in TIERS})
    down: set = field(default_factory=set)
    timeouts: set = field(default_factory=set)
    reply_text: object = None                            # str, or callable(request) -> str
    actual_input: object = None                          # callable(estimate) -> provider-reported input tokens
    rates: dict = field(default_factory=lambda: dict(DEFAULT_RATES))
    idem_store: dict = field(default_factory=dict)

    def __post_init__(self):
        self.spent = {k: 0 for k in self.layers}
        self.reservations: list = []
        self.events: list = []
        self.attempt_log: list = []
        self.overruns: list = []
        self.last_prompt = ""
        self._inflight: set = set()
        self._tainted_threads: set = set()

    # -- public -----------------------------------------------------------------------------------------------------
    def complete(self, request: dict) -> dict:
        cid = request.get("call_id") if isinstance(request, dict) else None
        call_id = cid if isinstance(cid, str) and ID_RE.match(cid) else None   # never echo other caller text
        self._validate(call_id, request)
        ns = (self.principal["service"], self.principal["tenant_id"], self.principal["actor_kind"],
              self.principal["actor_id"], request["idempotency_key"])
        if ns in self._inflight:
            raise ModelCallRefused(call_id, "invalid_request", "idempotency_in_flight")
        digest = _digest(request)
        if ns in self.idem_store:
            prev_digest, prev = self.idem_store[ns]
            if prev_digest != digest:
                raise ModelCallRefused(call_id, "invalid_request", "idempotency_conflict")
            return self._replay(call_id, prev)
        prompt = self._assemble(request, self._resolve(call_id, request))
        self.last_prompt = prompt
        self._gate(call_id, request, prompt)
        self._inflight.add(ns)
        try:
            reply = self._dispatch(call_id, request, prompt)
        finally:
            self._inflight.discard(ns)
        self.idem_store[ns] = (digest, reply)
        return reply

    # -- validation (schema first, then rules the schema cannot express) --------------------------------------------
    def _validate(self, call_id, r):
        bad = lambda reason: ModelCallRefused(call_id, "invalid_request", reason)  # noqa: E731
        try:                                  # lone surrogates and absurd nesting are invalid input, not crashes
            if not isinstance(r, dict) or len(_canon(r).encode("utf-8")) > MAX_REQUEST_BYTES:
                raise bad("schema")
            if next(_validator().iter_errors(r), None) is not None:
                raise bad(_classify(r))
        except (UnicodeError, RecursionError, ValueError):
            raise bad("schema") from None
        ids = [b["content_id"] for b in r["blocks"]]
        names = [t["name"] for t in r.get("tools", [])]
        if len(set(ids)) != len(ids) or len(set(names)) != len(names):
            raise bad("schema")                                   # duplicate content_id or tool
        mx = r["max_output_tokens"]
        if r.get("min_output_tokens", mx) > mx:
            raise bad("limit")
        last_rank, last_turn = 0, -1
        for b in r["blocks"]:
            rank = min(TRUST_ORDER.index(b["trust"]), 2)      # user and untrusted share the conversation rank
            if rank < last_rank or (rank == 2 and b["turn"] < last_turn):
                raise bad("block_order")
            last_rank, last_turn = rank, b.get("turn", last_turn)
        c, p = r["caller"], self.principal
        if any(b["trust"] == "user" for b in r["blocks"]) and p["actor_kind"] != "user" and not p.get("on_behalf_of"):
            raise bad("caller_mismatch")                          # a user-trust label needs a user principal
        if ({k: c[k] for k in IDENTITY_FIELDS if k in c} != {k: p[k] for k in IDENTITY_FIELDS if p.get(k) is not None}
                or sorted(c["role_ids"]) != sorted(p.get("role_ids", []))):
            raise bad("caller_mismatch")

    def _resolve(self, call_id, r):
        """Platform and tenant-config content and tool specs come from the registry, never from the body."""
        def refuse(reason):
            return ModelCallRefused(call_id, "invalid_request", reason)
        reg, pv, tenant = self.registry, r["prompt_version"], self.principal["tenant_id"]
        if pv not in reg.get("active_releases", {}).get(self.principal["service"], ()):
            raise refuse("ref_mismatch")                           # release not active for this service identity
        grant = set(self.principal.get("tool_grant", ()))          # from the signed run token
        texts = {}
        for i, b in enumerate(r["blocks"]):
            if b["trust"] not in REF_TRUST:
                continue
            if b["trust"] == "platform":
                e = reg["platform"].get((pv, b["content_id"]))
            else:
                applied = reg["applied_revision"].get(tenant)
                if applied is None:
                    raise refuse("unknown_ref")
                if b["revision_id"] != applied:
                    raise refuse("ref_mismatch")
                e = reg["tenant_config"].get((tenant, applied, b["content_id"]))
            if e is None:
                raise refuse("unknown_ref")
            if b["data_class"] != e["data_class"] or b.get("content_hash", content_hash(e["text"])) != content_hash(
                    e["text"]):
                raise refuse("ref_mismatch")
            texts[i] = e["text"]
        tools = []
        for t in r.get("tools", []):
            spec = reg["tools"].get((pv, t["name"]))
            if spec is None:
                raise refuse("unknown_ref")
            if t["name"] not in grant:
                raise refuse("ref_mismatch")                       # offered = manifest tools within the run grant
            if t.get("content_hash", tool_hash(spec)) != tool_hash(spec):
                raise refuse("ref_mismatch")
            tools.append(spec)
        return texts, tools

    def _assemble(self, r, resolved):
        """The prompt as sent. The real gateway uses a per-call random delimiter; the fake derives one."""
        texts, tools = resolved
        delim = "DATA-" + _digest(r)[:12]
        parts = []
        for i, b in enumerate(r["blocks"]):
            if i in texts:
                parts.append(f"[{b['trust']}:{b['content_id']}]\n{texts[i]}")
            elif b["trust"] == "untrusted":
                body = b["text"].replace(delim, delim + "_")
                parts.append(f"<<{delim} id={b['content_id']} role={b['role']} turn={b['turn']}>>\n{body}\n"
                             f"<<end {delim}>>")
            else:
                parts.append(f"[{b['role']} turn {b['turn']}]\n{b['text']}")
        parts.extend("[tool]\n" + _canon(s) for s in tools)
        return "\n".join(parts)

    def _flagged(self, text: str) -> bool:
        return bool(_SECRET.search(text)) or any(fp in text for fp in self.extra_fingerprints)

    def _gate(self, call_id, r, prompt):
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
        joined = "".join(b["text"] for b in r["blocks"] if "text" in b)    # secrets split across blocks
        if any(self._flagged(s) for s in [*_strings(r), prompt, joined]):
            raise ModelCallRefused(call_id, "filter_blocked", "flagged")     # one generic reason (ADR-0038)
        if not self.meter_up:
            raise ModelCallRefused(call_id, "budget_refused", "meter_unavailable")
        if any(self.budgets.get(k) is None for k in self.layers):
            raise ModelCallRefused(call_id, "budget_refused", "policy_missing")
        if any(self.principal.get(LAYER_ID[k]) is None for k in self.layers):
            raise ModelCallRefused(call_id, "budget_refused", "layer_unbound")

    def _replay(self, call_id, reply):
        """A stored reply is returned only if it would still pass the kill switch and the output filter."""
        if self.kill_switch is None:
            raise ModelCallRefused(call_id, "kill_switch_engaged", "unreachable")
        if self.kill_switch:
            raise ModelCallRefused(call_id, "kill_switch_engaged", "engaged")
        if not self.filter_up:
            raise ModelCallRefused(call_id, "filter_blocked", "filter_unavailable")
        if self._flagged(reply["text"]) or any(self._flagged(_canon(t)) for t in reply["tool_calls"]):
            raise ModelCallRefused(call_id, "filter_blocked", "flagged")
        return dict(reply, replayed=True)

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

    def _commit(self, res, cost):
        """Actual spend is real: commit it even above the hold, and record the overrun."""
        res.state, res.committed = "committed", cost
        if cost > res.amount:
            self.overruns.append((res.call_id, res.amount, cost))
        for k in self.layers:
            self.spent[k] += cost

    def _dispatch(self, call_id, r, prompt):
        est_in = len(prompt.encode("utf-8")) + FRAMING_TOKENS * (len(r["blocks"]) + len(r.get("tools", [])))
        chain = self._chain(r["tier"])
        if not chain:
            raise ModelCallRefused(call_id, "region_policy_refused", "no_allowed_endpoint")
        charged = False
        for attempt, entry in enumerate(chain, 1):
            try:
                res, limit = self._reserve(call_id, entry, r, est_in)
            except ModelCallRefused as exc:
                exc.reservation_released = not charged          # an earlier attempt was charged: say so
                raise
            if entry.name in self.down:                       # provider got nothing: release, fall back
                self.attempt_log.append((call_id, entry.name, "transport"))
                res.state = "released"
                continue
            if entry.name in self.timeouts:                   # sent, no answer: the provider may bill; charge the hold
                self.attempt_log.append((call_id, entry.name, "timeout"))
                self._commit(res, res.amount)
                self._meter(r, entry, est_in, limit, res.amount)
                charged = True
                continue
            self.attempt_log.append((call_id, entry.name, "ok"))
            text = self.reply_text(r) if callable(self.reply_text) else self.reply_text
            text = text if isinstance(text, str) else "fake:" + _digest(r)[:16]
            inp = self.actual_input(est_in) if callable(self.actual_input) else est_in
            wanted = max(1, -(-len(text.encode("utf-8")) // 3))
            out = min(limit, wanted)
            cost = self._cost(entry.tier, inp, out)
            self._commit(res, cost)
            event_id = self._meter(r, entry, inp, out, cost)
            if self._flagged(text):                           # content withheld, cost already committed
                raise ModelCallRefused(call_id, "filter_blocked", "flagged", reservation_released=False)
            keys = self._thread_keys()
            tainted = (r["thread_tainted"] or any(k in self._tainted_threads for k in keys)
                       or any(b["trust"] == "untrusted" for b in r["blocks"]))
            if tainted:
                self._tainted_threads.update(keys)            # sticky per thread, session and run (SEC-003 2.4 rule 4)
            return {"kind": "reply", "call_id": call_id, "idempotency_key": r["idempotency_key"],
                    "tier": entry.tier, "text": text, "tool_calls": [],
                    "stop_reason": "max_output" if wanted > limit else "end",
                    "trust": "untrusted", "tainted": tainted,
                    "usage": {"input_tokens": inp, "output_tokens": out, "cached_tokens": 0, "cost_micro_usd": cost},
                    "attempts": attempt, "fallback_used": attempt > 1, "meter_event_id": event_id, "replayed": False}
        raise ModelCallRefused(call_id, "model_unavailable", "chain_exhausted", reservation_released=not charged)

    def _thread_keys(self):
        p = self.principal
        return [(p["tenant_id"], kind, p[kind + "_id"]) for kind in ("thread", "session", "run") if p.get(kind + "_id")]

    def _meter(self, r, entry, inp, out, cost):
        p = self.principal
        event_id = "01HZZZZZZZZZZZZZZZZZ" + f"{len(self.events) + 1:06d}"
        self.events.append({
            "event_id": event_id, "type": "meter.ai_usage", "schema_version": 1, "occurred_at": FIXED_TS,
            "recorded_at": FIXED_TS, "tenant_id": p["tenant_id"],
            "actor": {"kind": p["actor_kind"], "id": p["actor_id"], "role_ids": list(p.get("role_ids", [])),
                      "on_behalf_of": p.get("on_behalf_of")},
            "source": {"service": "gateway"}, "correlation_id": r["caller"]["correlation_id"], "causation_id": None,
            "subject": None, "data_class": "operational",
            "data": {"model_id": entry.name, "tier": entry.tier, "input_tokens": inp, "output_tokens": out,
                     "cached_tokens": 0, "cost_micro_usd": cost, "purpose": r["purpose"],
                     "agent_id": p.get("agent_id")},
            "trace": {"model_id": entry.name, "prompt_version": r["prompt_version"]}})
        return event_id


def _classify(r: dict) -> str:
    """Map a schema failure to its most specific contract reason."""
    meta = r.get("metadata") if isinstance(r.get("metadata"), dict) else {}
    blocks = r.get("blocks") if isinstance(r.get("blocks"), list) else []
    tools = r.get("tools") if isinstance(r.get("tools"), list) else []
    if FORBIDDEN_FIELDS & (set(r) | set(meta)):
        return "model_named"
    if any(k.lower().startswith("tenant") for k in meta) or any(isinstance(b, dict) and "tenant_id" in b
                                                                 for b in blocks):
        return "tenant_in_payload"
    if any(not isinstance(b, dict) or b.get("trust") not in TRUST_ORDER for b in blocks):
        return "missing_trust_label"
    if any(b.get("trust") in REF_TRUST and "text" in b for b in blocks) or any(
            isinstance(t, dict) and ({"description", "input_schema"} & set(t)) for t in tools):
        return "ref_required"
    return "schema"


def _strings(doc):
    if isinstance(doc, str):
        yield doc
    elif isinstance(doc, dict):
        for k, v in doc.items():
            yield str(k)
            yield from _strings(v)
    elif isinstance(doc, list):
        for v in doc:
            yield from _strings(v)


def _digest(r: dict) -> str:
    return hashlib.sha256(_canon(r).encode("utf-8")).hexdigest()
