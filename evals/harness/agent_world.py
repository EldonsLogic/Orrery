"""QA-005: the offline world the agent-behaviour cases run in. Real platform code (runtime loop, allow-list, authority
rules, chat service, intent router, change-by-chat), fake ports only: a scripted model, a scripted Tool API port, an
in-memory Blueprint store and a scripted drafter. No model call, no network, no clock, no randomness.

Needs services/operate on the path; `ensure_path` adds it (same list the service tests use)."""
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OPERATE = os.path.join(REPO, "services", "operate")
_PATHS = (OPERATE, os.path.dirname(OPERATE), os.path.join(REPO, "services", "blueprint", "events"))
FIXTURE = os.path.join(REPO, "services", "blueprint", "fixtures", "trading-distribution.blueprint.json")
TENANT = "t_eval"
PRINCIPALS = {  # name -> (user id, roles). Roles come from the verified principal, never from a case's model script.
    "owner": ("u_owner", ("owner",)),
    "owner2": ("u_owner2", ("owner",)),
    "sales": ("u_sales", ("sales",)),
}


def ensure_path() -> None:
    for p in reversed(_PATHS):
        if p not in sys.path:
            sys.path.insert(0, p)


ensure_path()

from agui.ports import Principal  # noqa: E402
from change import ChangeService  # noqa: E402
from chat import ChatService, MemoryChatStore  # noqa: E402
from chat.router import IntentRouterAdapter  # noqa: E402
from router import IntentRouter  # noqa: E402
from runtime import (AgentLoop, AssistantConfig, Caller, Limits, MemoryTraceStore, ModelReply, SequentialIds,  # noqa: E402
                     TickClock, ToolCall, ToolResponse, Usage, resolve_allowlist)


def load_json(path: str):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ---- fake ports --------------------------------------------------------------------------------------------------
class ScriptedModel:
    """Each item is a reply dict {text, calls:[[name, args]], tokens:[in, out], cost}. The last item repeats."""
    model_id, prompt_version = "eval-scripted", "p0"

    def __init__(self, replies):
        self.replies, self.requests = list(replies or [{"text": ""}]), []

    def complete(self, request):
        self.requests.append(request)
        r = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        tin, tout = r.get("tokens", (100, 50))
        calls = tuple(ToolCall(f"c{i}", n, a) for i, (n, a) in enumerate(r.get("calls", ())))
        return ModelReply(r.get("text", ""), calls, Usage(tin, tout, 0, r.get("cost", 10), self.model_id, "mid"))


class ScriptedTools:
    """Tool API port fake. Records every request that reaches it: that is what 'dispatched' means in the cases."""

    def __init__(self, results, supports_propose=True):
        self.results, self.requests, self.supports_propose = results or {}, [], supports_propose

    def call(self, req):
        self.requests.append(req)
        r = self.results.get(req.tool) or {"status": "ok", "result": {"id": "X-1"}}
        if req.propose and r["status"] != "error":  # a propose call parks an approval and executes nothing
            return ToolResponse("pending_approval", approval={"id": "apr_" + req.idempotency_key[-6:]}, audit_id="aud_p")
        return ToolResponse(r["status"], r.get("result"), r.get("approval"), r.get("error"), "aud_1")


class ListSink:
    def __init__(self):
        self.items = []

    def emit(self, tenant_id, subject, type, data, trace):
        self.items.append((type, data))

    def types(self):
        return [t for t, _ in self.items]


# ---- runtime world -----------------------------------------------------------------------------------------------
def run_world(case: dict, catalog: list, arm: str = "scripted") -> dict:
    """Run one 'run' case through the real AgentLoop. Returns the observations the expectations are checked against."""
    roles = tuple(case.get("roles", ["sales"]))
    a = case.get("assistant")
    assistant = None if not a else AssistantConfig(
        a["id"], tuple(a["roles"]), tuple((n, bool(c)) for n, c in a["tools"]), a.get("max_tool_calls"),
        tuple((n, tuple(ids)) for n, ids in a.get("transitions", [])))
    allow = resolve_allowlist(catalog, roles, assistant)
    model = ScriptedModel([{"text": "ok"}] if arm == "silent" else case["model"])
    tools = ScriptedTools(case.get("tool_results"), case.get("propose", True))
    traces, sink = MemoryTraceStore(), ListSink()
    loop = AgentLoop(model=model, tools=tools, allow=allow, limits=Limits(**case.get("limits", {})), clock=TickClock(),
                     ids=SequentialIds(), traces=traces, events=sink, hash_salt=b"eval-salt")
    from runtime import TaintState
    taint = TaintState(True, ("session:earlier_turn",)) if case.get("taint") else None
    caller = Caller(TENANT, "u_eval", roles, "s_eval")
    res = loop.run(caller=caller, run_id="run_eval", user_text=case["user_text"], instructions="SYSTEM-INSTRUCTIONS",
                   locale=case.get("locale", "en"), taint=taint)
    spans = traces.spans(TENANT, "run_eval")
    return {"result": res, "requests": model.requests, "dispatched": tools.requests, "events": sink.types(),
            "tool_spans": [(s.tool, s.outcome) for s in spans if s.kind == "tool"],
            "menu": [t.name for t in (model.requests[0].tools if model.requests else ())]}


# ---- chat world --------------------------------------------------------------------------------------------------
class ScriptedDrafter:
    def __init__(self):
        self.out = []

    def draft(self, request):
        return self.out


class FakeBlueprints:
    def __init__(self):
        self.bp, self.submitted = load_json(FIXTURE), []

    def current(self, tenant_id):
        import copy
        return copy.deepcopy(self.bp)

    def validation_context(self, tenant_id):
        return None

    def submit_change(self, tenant_id, diff, proposal_digest, idempotency_key, *, actor, risk):
        self.submitted.append((tenant_id, diff, proposal_digest))
        return {"ok": True}

    def change_status(self, tenant_id, idempotency_key):
        return "unknown"


class _Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


class _Runtime:
    model_id, prompt_version = "eval-ordinary", "p0"

    def run(self, ctx):
        mid = "m_ord"
        return [{"type": "TEXT_MESSAGE_START", "messageId": mid, "role": "assistant"},
                {"type": "TEXT_MESSAGE_CONTENT", "messageId": mid, "delta": "ORDINARY-RUN"},
                {"type": "TEXT_MESSAGE_END", "messageId": mid}]


class ChatWorld:
    """One ChatService with change-by-chat on. `ordinary_runs` counts turns that reached the (fake) model runtime."""

    def __init__(self):
        self.clock, self.bps, self.drafter = _Clock(), FakeBlueprints(), ScriptedDrafter()
        self.ordinary_runs = 0
        self.change = ChangeService(blueprints=self.bps, drafter=self.drafter, clock=self.clock,
                                    allowed_roles={"owner"}, audit=lambda e: None)

        def factory(setup):
            self.ordinary_runs += 1
            return _Runtime()
        self.svc = ChatService(store=MemoryChatStore(), runtime_factory=factory, ids=SequentialIds(), clock=self.clock,
                               router=IntentRouterAdapter(IntentRouter()), change=self.change)
        self.sessions, self.n = {}, 0

    def principal(self, name):
        uid, roles = PRINCIPALS[name]
        return Principal(TENANT, uid, roles, "tok_" + name)

    def session(self, name, new=False):
        key = name
        if new or key not in self.sessions:
            self.sessions[key] = self.svc.open_session(self.principal(name), new=new).session_id
        return self.sessions[key]

    def say(self, name, text, message_id=None):
        self.n += 1
        mid = message_id or f"msg-{self.n:04d}-evalcase"
        events = list(self.svc.send(self.principal(name), self.session(name), mid, text))
        reply = "".join(e["delta"] for e in events if e["type"] == "TEXT_MESSAGE_CONTENT")
        return mid, reply, events

    def pending(self, name):
        p = self.principal(name)
        return self.svc.pending.get(p.tenant_id, p.subject, self.session(name))

    def proposal_active(self, name):
        p = self.principal(name)
        return self.change.store.active(p.tenant_id, p.subject, self.session(name)) is not None
