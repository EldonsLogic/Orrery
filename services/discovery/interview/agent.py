"""The interview state machine. Pure logic; the only outside call is the injected extraction port."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

from .catalog import Catalog, Question, ValueRejected, instantiate_module, validate_values
from .extract import (MAX_DOC_TEXT, MAX_OWNER_TEXT, clean_untrusted, detect_language, grounded, is_unknown,
                      parse_deterministic)
from .session import Session

MIN_CONFIDENCE = 0.6
# Defaults that name a rule of the template or country pack rather than a value to send to the instantiator.
SENTINELS = {"country_pack"}


class InterviewError(ValueError):
    """Misuse of the API (wrong question, finished session, over budget). Not an owner-facing message."""


class ExtractionPort(Protocol):
    """Injected model port. Receives untrusted text as data in `untrusted_text`; its reply is untrusted."""

    def extract(self, request: dict) -> Any: ...


@dataclass(frozen=True)
class Prompt:
    qid: str
    language: str
    section: str
    text: str
    options: tuple       # ((value, label), ...)
    index: int
    total: int

    def render(self) -> str:
        lines = [f"[{self.section}] {self.text}"]
        lines += [f"- {label}" for _, label in self.options]
        return "\n".join(lines)


@dataclass
class TurnResult:
    prompt: Optional[Prompt]
    accepted: list = field(default_factory=list)     # qids stored this turn
    flags: list = field(default_factory=list)        # flags raised this turn
    complete: bool = False


class Interviewer:
    def __init__(self, catalog: Catalog, port: Optional[ExtractionPort] = None, max_turns: int = 300,
                 max_port_calls: int = 100, max_retries: int = 2) -> None:
        self.catalog, self.port = catalog, port
        self.max_turns, self.max_port_calls, self.max_retries = max_turns, max_port_calls, max_retries

    # ------------------------------------------------------------------ lifecycle
    def start(self, session_id: str, language: str = "en") -> Session:
        if language not in ("ar", "en"):
            raise InterviewError("language must be ar or en")
        s = Session(session_id, language)
        self._advance(s)
        return s

    def prompt(self, s: Session) -> Optional[Prompt]:
        q = self.catalog.get(s.current) if s.current else None
        if q is None:
            return None
        lang = s.language
        opts = tuple((v, labels.get(lang) or labels.get("en", str(v))) for v, labels in q.options)
        return Prompt(q.id, lang, q.section_title.get(lang, q.section), q.text.get(lang) or q.text["en"], opts,
                      self.catalog.ids().index(q.id) + 1, len(self.catalog.questions))

    def _advance(self, s: Session) -> None:
        for q in self.catalog.questions:
            if q.id not in s.answers and s.retries.get(q.id, 0) <= self.max_retries:
                s.current, s.state = q.id, "asking"
                return
        s.current, s.state = None, "complete"

    # ------------------------------------------------------------------ owner turn
    def answer(self, s: Session, owner_text: str, qid: Optional[str] = None) -> TurnResult:
        """Process one owner message for the current question, or for `qid` (a correction)."""
        qid = qid or s.current
        q = self.catalog.get(qid) if qid else None
        if q is None:
            raise InterviewError("no question to answer")
        if s.turns >= self.max_turns:
            s.flag("budget", qid, "turn limit reached")
            raise InterviewError("turn limit reached")
        s.turns += 1
        mark = len(s.flags)
        text, hits = clean_untrusted(owner_text, MAX_OWNER_TEXT)
        if hits:
            s.flag("injection_suspected", qid, "instruction-like text in owner message: "
                   + ",".join(sorted({h[0] for h in hits})))
        s.language = detect_language(text, s.language)
        accepted: list = []
        if not text.strip():
            self._fail(s, q, "empty answer")
        elif is_unknown(text):
            self._use_default(s, q, accepted)
        else:
            values, confident = parse_deterministic(q, text), True
            try:
                values = validate_values(q, values) if values is not None else None
            except ValueRejected as e:
                s.flag("extraction_rejected", q.id, f"value rejected: {e}")
                values = None
                self._fail(s, q, "out of range")
                self._cross_checks(s)
                self._advance(s)
                return TurnResult(self.prompt(s), accepted, s.flags[mark:], s.state == "complete")
            if values is None:
                values, confident = self._ask_port(s, q, text, "owner")
            if values is not None and not grounded(q, values, text):
                s.flag("ungrounded", q.id, "model value not found in the owner's text; discarded")
                values = None
            if values is None:
                self._fail(s, q, "not understood")
            else:
                if not confident:
                    s.flag("uncertain", q.id, "low confidence; the owner must confirm")
                if self._store(s, q, values, "owner", "confirmed" if confident else "proposed", None):
                    accepted.append(q.id)
        self._cross_checks(s)
        self._advance(s)
        return TurnResult(self.prompt(s), accepted, s.flags[mark:], s.state == "complete")

    def _fail(self, s: Session, q: Question, why: str) -> None:
        s.retries[q.id] = s.retries.get(q.id, 0) + 1
        s.flag("extraction_rejected", q.id, why)

    def _use_default(self, s: Session, q: Question, accepted: list) -> None:
        s.flag("uncertain", q.id, "owner does not know")
        if q.default is None:
            s.retries[q.id] = s.retries.get(q.id, 0) + 1   # required with no default: ask again, then defer
            return
        key = q.keys[0]
        if len(q.keys) == 1 and q.id not in s.answers:
            s.answers[q.id] = {"values": {key: q.default}, "source": "template", "status": "default"}
            accepted.append(q.id)

    # ------------------------------------------------------------------ model port
    def _call(self, s: Session, request: dict) -> Any:
        if self.port is None:
            return None
        if s.port_calls >= self.max_port_calls:
            s.flag("budget", None, "model call limit reached")
            return None
        s.port_calls += 1
        try:
            return self.port.extract(request)
        except Exception as e:  # noqa: BLE001 - any port failure fails closed
            s.flag("extraction_rejected", request.get("question", {}).get("id"), f"model port error: {type(e).__name__}")
            return None

    @staticmethod
    def _qview(q: Question) -> dict:
        return {"id": q.id, "type": q.type, "answer_keys": list(q.keys), "options": q.option_values()}

    def _ask_port(self, s: Session, q: Question, text: str, source: str) -> tuple:
        """(values or None, confident). Anything malformed returns (None, True) after a flag."""
        reply = self._call(s, {"task": "extract_answer", "question": self._qview(q), "language": s.language,
                               "source": source, "untrusted_text": text})
        return self._check_reply(s, q, reply)

    def _check_reply(self, s: Session, q: Question, reply: Any) -> tuple:
        if reply is None:
            return None, True
        try:
            if (not isinstance(reply, dict) or not set(reply) <= {"values", "confidence", "unsure"}
                    or "values" not in reply):
                raise ValueRejected("reply shape")
            conf, unsure = reply.get("confidence", 1.0), reply.get("unsure", False)
            if (isinstance(conf, bool) or not isinstance(conf, (int, float)) or not 0 <= conf <= 1
                    or not isinstance(unsure, bool)):
                raise ValueRejected("confidence or unsure")
            values = validate_values(q, reply["values"])
        except ValueRejected as e:
            s.flag("extraction_rejected", q.id, f"model output rejected: {e}")
            return None, True
        return values, not unsure and conf >= MIN_CONFIDENCE

    # ------------------------------------------------------------------ documents
    def ingest_document(self, s: Session, text: str, name: str = "document") -> TurnResult:
        """Owner-supplied document text. Values found become `proposed`; the owner confirms each one."""
        mark = len(s.flags)
        clean, hits = clean_untrusted(text, MAX_DOC_TEXT)
        label = clean_untrusted(name, 80)[0][:80] or "document"
        if hits:
            s.flag("injection_suspected", None, f"instruction-like text in {label}: "
                   + ",".join(sorted({h[0] for h in hits})))
        todo = list(self.catalog.questions)
        reply = self._call(s, {"task": "extract_document", "language": s.language, "source": "document",
                               "document_name": label, "untrusted_text": clean,
                               "questions": [self._qview(q) for q in todo]}) if clean.strip() and todo else None
        accepted: list = []
        found = reply.get("answers") if isinstance(reply, dict) and set(reply) == {"answers"} else None
        if reply is not None and not isinstance(found, dict):
            s.flag("extraction_rejected", None, "model output rejected: document reply shape")
            found = {}
        for qid, item in (found or {}).items():
            q = self.catalog.get(qid) if isinstance(qid, str) else None
            if q is None or q not in todo:
                s.flag("extraction_rejected", None, "model answered a question that was not asked")
                continue
            values, _ = self._check_reply(s, q, item)
            if values is not None and not grounded(q, values, clean):
                s.flag("ungrounded", q.id, "document value not found in the document; discarded")
                values = None
            if values is not None and self._store(s, q, values, "document", "proposed", label):
                accepted.append(q.id)
        self._cross_checks(s)
        self._advance(s)
        return TurnResult(self.prompt(s), accepted, s.flags[mark:], s.state == "complete")

    # ------------------------------------------------------------------ storing and review
    def _store(self, s: Session, q: Question, values: dict, source: str, status: str, doc: Optional[str]) -> bool:
        old = s.answers.get(q.id)
        if old and old["status"] == "confirmed" and old["values"] != values:
            s.pending[q.id] = values
            s.flag("contradiction", q.id, f"new {source} value differs from the confirmed one; kept the old")
            return False
        if old and old["status"] == "confirmed" and old["values"] == values:
            return False
        s.answers[q.id] = {"values": values, "source": source, "status": status, **({"doc": doc} if doc else {})}
        s.retries.pop(q.id, None)
        return True

    def confirm(self, s: Session, qid: str) -> None:
        a = s.answers.get(qid)
        if not a or a["status"] != "proposed":
            raise InterviewError("nothing proposed for that question")
        a["status"] = "confirmed"
        self._cross_checks(s)

    def reject(self, s: Session, qid: str) -> None:
        a = s.answers.get(qid)
        if not a or a["status"] != "proposed":
            raise InterviewError("nothing proposed for that question")
        del s.answers[qid]
        s.retries.pop(qid, None)
        self._advance(s)

    def resolve_contradiction(self, s: Session, qid: str, keep_new: bool) -> None:
        if qid not in s.pending:
            raise InterviewError("no open contradiction for that question")
        new = s.pending.pop(qid)
        if keep_new:
            s.answers[qid] = {"values": new, "source": "owner", "status": "confirmed"}
            self._cross_checks(s)

    def _val(self, s: Session, qid: str, key: Optional[str] = None) -> Any:
        a = s.answers.get(qid)
        if not a or a["status"] != "confirmed":
            return None
        return a["values"].get(key or qid)

    def _cross_checks(self, s: Session) -> None:
        rules = [
            ("vat_number given but the company is not VAT registered", self._val(s, "q_vat_registered", "vat_registered") is False
             and self._val(s, "q_vat_number", "vat_number") is not None, "q_vat_number"),
            ("sales approver is the accountant but there is no finance department",
             self._val(s, "q_sales_approver") == "accountant" and self._val(s, "q_finance_department") is False,
             "q_sales_approver"),
        ]
        for detail, hit, qid in rules:
            if hit and not any(f["kind"] == "cross_check" and f["detail"] == detail[:200] for f in s.flags):
                s.flag("cross_check", qid, detail)

    # ------------------------------------------------------------------ output
    def draft_input(self, s: Session) -> dict:
        """Blueprint-draft input for the template instantiator. A proposal for a human; never a Blueprint."""
        answers, interview, proposed, defaults = {}, {}, {}, []
        for q in self.catalog.questions:
            a = s.answers.get(q.id)
            if not a:
                continue
            if a["status"] == "proposed":
                proposed[q.id] = {"values": a["values"], "source": a["source"], **({"doc": a["doc"]} if "doc" in a else {})}
                continue
            if a["status"] == "default":
                defaults.append(q.id)
            if q.fills_by == "instantiate":
                answers.update({k: v for k, v in a["values"].items() if not (isinstance(v, str) and v in SENTINELS)})
            else:
                interview[q.id] = a["values"][q.id]
        errors: list = []
        try:
            instantiate_module().check_answers(dict(answers))
        except Exception as e:  # noqa: BLE001 - InstantiationError from a script loaded by path
            errors.append(str(e))
        missing = [q.id for q in self.catalog.questions if q.required and q.id not in s.answers]
        ready = not (errors or missing or proposed or s.pending)
        return {"status": "draft", "requires_owner_approval": True, "template": dict(self.catalog.template),
                "answers": answers, "interview": interview, "proposed": proposed, "defaults_used": defaults,
                "open_contradictions": sorted(s.pending), "unanswered_required": missing,
                "validation_errors": errors, "flags": [dict(f) for f in s.flags], "ready": ready}
