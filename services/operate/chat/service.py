"""Chat service (OPR-010): sessions, one-run-per-session streaming, Arabic and English, audit without bodies.

`send` is a generator of allow-listed AG-UI event dicts (checked by `agui.events.sanitize`). Failures before or during
a run end the stream with one `RUN_ERROR` carrying a code and bilingual text from `errors.py`; nothing else leaks.
Roles and tenant come only from the verified `Principal`; the model and the client never supply them (ADR-0004)."""
from __future__ import annotations

import hashlib
import logging
import math
import re
import threading
from typing import Iterator, Optional

from agui import events as wire
from agui.ports import Principal, RuntimeContext
from runtime import CancelToken, RateLimited, RateLimiter

from . import errors, language
from change import ChangeRefused
from .errors import ChatFailure
from .history import build_window, default_frame
from .models import ChatLimits, Entry, MessageRecord, PendingBinding, RouteRequest, RunSetup, Session
from .router import DefaultRouter, safe_route
from .store import MemoryPendingStore, NoRetention

log = logging.getLogger("chat")
_MSG_ID = re.compile(r"^[A-Za-z0-9_\-:.]{8,128}$")
_STATE_KEYS = ("sessionId", "mode", "locale", "dir")


def _sha(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


class ChatService:
    def __init__(self, *, store, runtime_factory, ids, clock, audit=None, router=None, retention=None,
                 limits: ChatLimits = ChatLimits(), frame_for=default_frame, default_locale: str = "en",
                 change=None, pending=None, limiter=None):
        """`change` is a ChangePort (change.ChangeService) built on the SAME clock. With it, a `change` turn that the
        router says needs confirmation is proposed and previewed here, the pending confirmation is recorded only after
        the preview was shown, and a confirming turn goes to `change.confirm` with the router's binding. Without it
        the chat never proposes or confirms anything. `limiter` (SEC-009) counts accepted turns and new sessions per
        tenant and user; the default uses `runtime.ratelimit.DEFAULT_RULES` on the same clock (which must be
        monotonic). Share it with `loop_runtime_factory`."""
        self.store, self.factory, self.ids, self.clock, self.audit = store, runtime_factory, ids, clock, audit
        self.change, self.pending = change, pending or MemoryPendingStore()
        self.router, self.retention = router or DefaultRouter(), retention or NoRetention()
        self.limits, self.frame_for, self.default_locale = limits, frame_for, default_locale
        self.limiter = RateLimiter(clock) if limiter is None else limiter
        self._lock = threading.Lock()
        self._active: dict = {}  # (tenant, session_id) -> (run_id, CancelToken)

    # ---- sessions ------------------------------------------------------------------------------------------
    @staticmethod
    def _check(p: Principal) -> None:
        if not (isinstance(p, Principal) and p.tenant_id and p.subject and p.role_ids):
            raise ChatFailure("permission_denied")  # no tenant, user or roles: fail closed

    def open_session(self, p: Principal, session_id: Optional[str] = None, new: bool = False) -> Session:
        """Resume `session_id` (must be this user's), else the user's latest session, else create one."""
        self._check(p)
        if session_id:
            s = self.store.get_session(p.tenant_id, p.subject, session_id)
            if s is None:
                raise ChatFailure("chat_session_not_found")
            return s
        s = None if new else self.store.latest_session(p.tenant_id, p.subject)
        if s is not None:
            return s
        try:  # new sessions are metered per user, so a fresh session is not a fresh quota
            self._admit(p, "session")
        except ChatFailure as f:
            self._audit_refusal(p, f)
            raise
        now = self.clock()
        return self.store.create_session(Session(p.tenant_id, p.subject, self.ids.new_id("ses"),
                                                 self.ids.new_id("thr"), self.default_locale, now, now))

    def history(self, p: Principal, session_id: str) -> list:
        """Stored turns for the client to restore a conversation. Another user's session is not found."""
        return self.store.entries(self.open_session(p, session_id))

    def cancel(self, p: Principal, session_id: str) -> bool:
        """Stop the active run of this user's session. False when there is none."""
        s = self.open_session(p, session_id)
        with self._lock:
            cur = self._active.get((s.tenant_id, s.session_id))
        if cur is None:
            return False
        cur[1].cancel()
        return True

    def _admit(self, p: Principal, kind: str) -> None:
        """Count one `kind` event for the verified principal (SEC-009). Over a limit is retryable with a wait time;
        a limiter fault or misconfiguration is not, and says so. The first refusal per key and reason carries its
        audit record (no message text); the caller emits it outside the chat lock (`_audit_refusal`)."""
        try:
            self.limiter.admit(kind, p.tenant_id, p.subject)
        except RateLimited as e:
            if e.retryable:
                f = ChatFailure("chat_rate_limited", {"minutes": max(1, math.ceil(e.retry_after_s / 60))})
            else:
                f = ChatFailure("chat_limit_unavailable")
            if getattr(e, "first", True):
                f.audit = {"kind": kind, "reason": e.reason, "retry_after_s": e.retry_after_s}
            raise f

    def _audit_refusal(self, p: Principal, exc: BaseException) -> None:
        data = getattr(exc, "audit", None)
        if data:
            self._audit(p, "chat.rate_limited", data)

    # ---- audit ---------------------------------------------------------------------------------------------
    def _audit(self, p: Principal, type_: str, data: dict, trace: Optional[dict] = None) -> None:
        if self.audit is None:
            return
        try:
            self.audit.emit(p.tenant_id, p.subject, type_, data, trace)
        except Exception as exc:  # auditing never breaks a turn
            log.error("chat audit failed type=%s exc=%s", type_, type(exc).__name__)

    # ---- send ----------------------------------------------------------------------------------------------
    def send(self, p: Principal, session_id: str, message_id: str, text: str) -> Iterator[dict]:
        locale = self.default_locale
        try:
            yield from self._send(p, session_id, message_id, text)
        except GeneratorExit:
            raise
        except Exception as exc:
            err = errors.firewall(exc, locale)
            yield wire.run_error(err["message"], err["code"])

    def _send(self, p, session_id, message_id, text):
        self._check(p)
        if not isinstance(message_id, str) or not _MSG_ID.match(message_id):
            raise ChatFailure("chat_message_id_invalid")
        text = language.clean_text(text) if isinstance(text, str) else ""
        if not text.strip():
            raise ChatFailure("chat_message_empty")
        if len(text) > self.limits.max_message_chars:
            raise ChatFailure("chat_message_too_long")
        session = self.open_session(p, session_id)
        lang = language.detect(text, session.locale)
        thash, run_id, refused = _sha(text), self.ids.new_id("run"), None
        with self._lock:  # dedup and the one-run rule are decided together
            rec = self.store.get_message(session, message_id)
            if rec is not None and rec.text_hash != thash:
                raise ChatFailure("chat_message_id_conflict")
            replay = rec if rec is not None and rec.status == "done" else None
            if replay is None:
                if not self.store.begin_run(session, run_id, self.clock(), self.limits.run_ttl_s):
                    raise ChatFailure("chat_run_in_progress")  # second message is rejected, not queued
                try:  # only an accepted turn counts; a replay is free (SEC-009)
                    self._admit(p, "turn")
                except Exception as exc:
                    self.store.end_run(session, run_id)  # same lock: undo the accepted run before refusing
                    refused = exc
                else:
                    self.store.put_message(session, MessageRecord(message_id, thash, "running", "", run_id))
                    token = CancelToken()
                    self._active[(session.tenant_id, session.session_id)] = (run_id, token)
        if refused is not None:  # audited after the lock is released, so a flood cannot serialise other sends
            self._audit_refusal(p, refused)
            raise refused
        if replay is not None:
            yield from self._replay(session, replay, lang.locale)
            return
        final = {"status": "cancelled"}
        try:
            yield from self._run(p, session, message_id, text, thash, lang, run_id, token, final)
        finally:  # runs on completion, error and on a client that disconnects mid-stream
            token.cancel()
            self.store.put_message(session, MessageRecord(message_id, thash, final["status"],
                                                          final.get("assistant_id", ""), run_id))
            self.store.end_run(session, run_id)
            with self._lock:
                self._active.pop((session.tenant_id, session.session_id), None)

    def _replay(self, session, rec, locale):
        reply = next((e for e in self.store.entries(session) if e.message_id == rec.assistant_message_id), None)
        yield wire.run_started(session.thread_id, rec.run_id or "replay")
        if reply is not None and reply.text:
            mid = rec.assistant_message_id
            yield {"type": "TEXT_MESSAGE_START", "messageId": mid, "role": "assistant"}
            yield {"type": "TEXT_MESSAGE_CONTENT", "messageId": mid, "delta": reply.text}
            yield {"type": "TEXT_MESSAGE_END", "messageId": mid}
        yield wire.run_finished(session.thread_id, rec.run_id or "replay")

    def _run(self, p, session, message_id, text, thash, lang, run_id, token, final):
        lim = self.limits
        t0 = self.clock()
        pend = self.pending.get(p.tenant_id, p.subject, session.session_id) if self.change is not None else None
        routed = safe_route(self.router, RouteRequest(p.tenant_id, p.subject, tuple(p.role_ids), session.session_id,
                                                      text, lang.locale, "ask", pend, t0))
        mode = routed.mode
        direct = self._change_turn(p, session, text, lang, routed, pend) if self.change is not None else None
        prior = [e for e in self.store.entries(session) if e.message_id != message_id]
        window = build_window(prior, self.frame_for(mode, lang.locale), lim)
        if all(e.message_id != message_id for e in self.store.entries(session)):  # a retry must not duplicate it
            self.retention.on_append(session, self.store.append(session, Entry(0, "user", text, message_id,
                                                                               lang.locale)))
        self.store.save_session(Session(**{**session.__dict__, "locale": lang.locale, "last_active": self.clock()}))
        self._audit(p, "chat.message_received", {
            "session_id": session.session_id, "message_id": message_id, "run_id": run_id, "text_sha256": thash,
            "text_len": len(text), "locale": lang.locale, "mixed": lang.mixed, "mode": mode})
        log.info("chat message session=%s len=%d locale=%s mode=%s", session.session_id, len(text), lang.locale, mode)
        runtime = None if direct is not None else self.factory(RunSetup(window, mode, lang.locale, token))
        ctx = RuntimeContext(principal=p, thread_id=session.thread_id, run_id=run_id, user_text=text,
                             server_state={"mode": mode, "numbers": language.extract_numbers(text, lim.max_numbers)},
                             locale=lang.locale)
        yield wire.run_started(session.thread_id, run_id)
        yield {"type": "STATE_SNAPSHOT", "snapshot": {"chat": {"sessionId": session.session_id, "mode": mode,
                                                                "locale": lang.locale, "dir": lang.direction}}}
        yield wire.custom("tool.progress", {"phase": "typing"})
        parts, opened, approvals, usage, error = [], set(), [], [0, 0], None
        it = None
        try:
            it = iter(direct if direct is not None else runtime.run(ctx))
            for item in it:
                if token.cancelled:
                    break
                if isinstance(item, dict):
                    ev = self._scrub(item)
                    if ev is None:
                        continue
                    t = ev["type"]
                    if t == "TEXT_MESSAGE_START":
                        opened.add(ev["messageId"])
                    elif t == "TEXT_MESSAGE_END":
                        opened.discard(ev["messageId"])
                    elif t == "TEXT_MESSAGE_CONTENT":
                        parts.append(ev["delta"])
                    elif t == "CUSTOM" and ev["name"] == "approval.pending":
                        approvals.append(str(ev["value"].get("approvalId", "")))
                    yield ev
                else:  # RuntimeUsage
                    usage[0] += int(getattr(item, "input_tokens", 0))
                    usage[1] += int(getattr(item, "output_tokens", 0))
        except Exception as exc:
            error = errors.firewall(exc, lang.locale)
        finally:
            close = getattr(it, "close", None)
            if close:
                close()
        for mid in sorted(opened):
            yield {"type": "TEXT_MESSAGE_END", "messageId": mid}
        cancelled = token.cancelled and error is None
        reply = "".join(parts)
        aid = self.ids.new_id("msg")
        if reply:
            self.retention.on_append(session, self.store.append(session, Entry(0, "assistant", reply, aid,
                                                                               lang.locale, cancelled)))
        final["status"] = "cancelled" if cancelled else ("failed" if error else "done")
        final["assistant_id"] = aid if reply else ""
        outcome = final["status"]
        self._audit(p, "chat.message_sent", {
            "session_id": session.session_id, "message_id": aid, "in_reply_to": message_id, "run_id": run_id,
            "text_sha256": _sha(reply), "text_len": len(reply), "locale": lang.locale, "outcome": outcome})
        self._audit(p, "chat.turn_completed", {
            "mode": mode, "latency_ms": max(0, int(round((self.clock() - t0) * 1000))),
            "input_tokens": usage[0], "output_tokens": usage[1]},
            {"model_id": str(getattr(runtime, "model_id", "change-service" if direct is not None else "unknown"))[:256],
             "prompt_version": str(getattr(runtime, "prompt_version", "unversioned"))[:256]})
        if cancelled:
            e = errors.render("chat_cancelled", lang.locale)
            yield wire.run_error(e["message"], "cancelled")
        elif error:
            yield wire.run_error(error["message"], error["code"])
        else:
            yield wire.run_finished(session.thread_id, run_id, [wire.interrupt(a) for a in approvals if a])

    # ---- change-by-chat (Q-265, Q-282) -----------------------------------------------------------------------
    def _change_turn(self, p, session, text, lang, routed, pend):
        """Return a deterministic reply generator for turns the change service owns, else None (the model runs).
        Owns: a confirmation bound to the pending preview, a refused or expired one, and a new change request."""
        key = (p.tenant_id, p.subject, session.session_id)
        res = routed.resolves_pending
        if res in ("declined", "expired"):
            self.pending.clear(*key)
            self._cancel_quietly(p, session.session_id)
            return None  # an ordinary turn follows (the router already abstained or answered ask)
        if res == "confirmed" or (routed.confirms_action_id and routed.confirms_args_hash):
            self.pending.clear(*key)  # one shot, whatever happens next
            return self._confirm_events(p, session, lang, routed, pend)
        if pend is not None:  # any turn that does not answer the pending voids it: a later yes must not apply it
            self.pending.clear(*key)
            self._cancel_quietly(p, session.session_id)
        if routed.mode == "change" and routed.requires_confirmation and routed.decision is not None:
            self.pending.clear(*key)  # a new request voids the old pending before its own preview exists
            return self._propose_events(p, session, text, lang, routed)
        return None

    def _cancel_quietly(self, p, session_id) -> None:
        try:
            self.change.cancel(p, session_id)
        except Exception as exc:  # noqa: BLE001
            log.error("change cancel failed type=%s", type(exc).__name__)

    def _text(self, text: str) -> list:
        mid = self.ids.new_id("msg")
        return [{"type": "TEXT_MESSAGE_START", "messageId": mid, "role": "assistant"},
                {"type": "TEXT_MESSAGE_CONTENT", "messageId": mid, "delta": text},
                {"type": "TEXT_MESSAGE_END", "messageId": mid}]

    def _refusal_text(self, exc: Exception, locale: str) -> str:
        return (exc if isinstance(exc, ChangeRefused) else ChangeRefused("change_unavailable")).text(locale)

    def _confirm_events(self, p, session, lang, routed, pend):
        sid, locale = session.session_id, lang.locale
        try:
            bound = (pend is not None and routed.decision is not None and routed.mode == pend.mode
                     and routed.confirms_action_id == pend.action_id and routed.confirms_args_hash == pend.args_hash)
            if not bound:  # the chat's own pending is the only thing a yes can confirm
                raise ChangeRefused("change_confirmation_mismatch")
            out = self.change.confirm(p, sid, routed.decision, locale)
            reply = out.text
        except Exception as exc:  # noqa: BLE001  only the closed table reaches the customer
            reply = self._refusal_text(exc, locale)
        yield from self._text(reply)

    def _propose_events(self, p, session, text, lang, routed):
        sid, locale = session.session_id, lang.locale
        try:
            pv = self.change.propose(p, sid, text, routed.decision, locale)
            binding = PendingBinding("change", pv.action_id, pv.digest, pv.risk, pv.expires_at)
        except Exception as exc:  # noqa: BLE001
            yield from self._text(self._refusal_text(exc, locale))
            return
        lines = [pv.text] + [f"- {o['pointer']}: {o['before']} -> {o['after']}" for o in pv.ops]
        events = self._text("\n".join(lines))
        # the output gate may drop the preview (engine markers in tenant-typed values): then it was not shown
        if any(self._scrub(e) != e for e in events):
            self._cancel_quietly(p, sid)
            yield from self._text(self._refusal_text(ChangeRefused("change_preview_failed"), locale))
            return
        yield from events
        # reached only when the consumer asked for more after the last preview event: the user was shown the preview
        self.pending.set(p.tenant_id, p.subject, sid, binding)

    @staticmethod
    def _scrub(ev: dict) -> Optional[dict]:
        """Bidi-clean assistant text, then the allow-list gate. Anything that fails either is dropped."""
        if ev.get("type") == "TEXT_MESSAGE_CONTENT" and isinstance(ev.get("delta"), str):
            ev = {**ev, "delta": language.clean_text(ev["delta"])}
        out = wire.sanitize(ev)
        if out is not None and out["type"] in ("RUN_STARTED", "RUN_FINISHED", "RUN_ERROR"):
            return None  # the chat service owns the run envelope
        return out
