"""Deterministic bilingual rules (stage 1). Input is the normalised user turn only (see text.normalise).

Signals: explicit slash command at the very start, interrogative or read form, imperative or desire plus an action
verb, configuration nouns (change), business nouns and Blueprint entity names (act), discovery phrases. Every
pattern is bounded (no nested quantifiers) and the input is capped by `text.MAX_CHARS`."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .models import max_risk
from .text import normalise

_FILLER = re.compile(r"^(?:(?:please|pls|kindly|hey|ok|okay|so|well|then|now|طيب|الحين|الان|يلا|لو سمحت|من فضلك) )+")
SLASH = re.compile(r"^/(ask|act|change|discover|اسال|نفذ|غير|اكتشف)(?: |$)")
_SLASH_MODE = {"ask": "ask", "act": "act", "change": "change", "discover": "discover",
               "اسال": "ask", "نفذ": "act", "غير": "change", "اكتشف": "discover"}
# Prose that tries to talk to the router. It never sets a mode; the clause is cut and the turn is capped at ask.
META = re.compile(
    r"(?:ignore|disregard|forget|override|bypass)\b[^.;!\n]{0,40}\b(?:instructions?|rules?|polic(?:y|ies)|safety|"
    r"restrictions?|prompt)|\b(?:switch|change|go|move|set)\b[^.;!\n]{0,12}\b(?:to|into)\b[^.;!\n]{0,12}\bmode\b|"
    r"\b(?:enter|enable|activate|you are now in)\b[^.;!\n]{0,12}\bmode\b|\bsystem prompt\b|\bdeveloper mode\b|"
    r"\byou are now\b|\bfrom now on\b|\bact as (?:an? )?(?:admin|root|owner)\b|\bmode\s*[:=]\s*(?:ask|act|change|discover)\b|"
    r"تجاهل[^.;!\n]{0,30}(?:التعليمات|الاوامر|القواعد)|(?:انتقل|غير|حول)[^.;!\n]{0,12}الي وضع|وضع (?:التغيير|التنفيذ)|"
    r"من الان فصاعدا")
_POLITE = re.compile(r"^(?:(?:can|could|would|will) you\b|is it possible\b|i was wondering\b|do you mind\b|"
                     r"ممكن|تقدر|تقدرون|هل (?:تقدر|يمكن|بامكانك)|يمكنك|بامكانك)")
_QUESTION = re.compile(r"^(?:what|which|who|whom|whose|when|where|why|how|is|are|do|does|did|was|were|has|have|"
                       r"should|shall|if|suppose|any|كم|كام|ما|ماذا|متي|امتي|اين|فين|كيف|ازاي|لماذا|ليش|ليه|هل|وش|شو|ايش|"
                       r"مين|قديش|لو|اذا)(?: |$)")
_READ = re.compile(r"^(?:show|list|display|view|find|search|look ?up|get me|give me (?:the |a )?(?:report|list|"
                   r"summary|balance|total|status)|tell me|check|convert|summari[sz]e|export|print|calculate|compare|"
                   r"explain|describe|run (?:the |a )?(?:[a-z ]{0,25})(?:report|query|summary|balance)|"
                   r"اعرض|اعرضلي|اظهر|ابحث|استعلم|اطلع|هات|عطني|وريني|لخص|احسب|قارن|اشرح|"
                   r"(?:ابي|ابغي|ودي|عايز|عايزه|بدي|اريد|نبي) (?:ان )?(?:اعرف|اشوف|اطلع|استعلم))(?: |$)")
_READ_OBJ = re.compile(r"trial balance|\breport\b|\bsummary\b|\bstatement\b|ملخص|تقرير|ميزانيه|كشف حساب")
_ACT_VERB = (r"(?:create|make|draft|issue|add|post|record|register|send|submit|cancel|approve|reject|void|delete|"
             r"remove|update|set|pay|receive|return|transfer|book|log|enter|raise|generate|reverse|refund|edit|"
             r"change|modify|mark|close|reopen|assign|"
             r"انشئ|انشي|اعمل|سو|سوي|اصدر|سجل|اضف|اضيف|ضيف|ارسل|الغ|الغي|امسح|احذف|اعتمد|وافق|ارفض|ارجع|ادفع|"
             r"اعد|غير|عدل|حدث|خلي)")
_DESIRE = (r"(?:i want to|i need to|i would like to|i'd like to|we need to|we want to|let's|lets|go ahead and|"
           r"ابغي ان|ابي ان|ابغي|ابي|ودي ان|ودي|عايز ان|عايزه|عايز|بدي|اريد ان|اريد|نبي|نحتاج ان|احتاج ان)")
_IMPERATIVE = re.compile(rf"^(?:{_DESIRE} (?:to )?)?{_ACT_VERB}(?: |$)")
_ACT_ANYWHERE = re.compile(rf"(?:^| )(?:and |then |ثم |و)?{_ACT_VERB}(?: |$)")
_THEN_ACT = re.compile(rf"(?: and | then | ثم | و ?|, ?|; ?){_ACT_VERB}(?: |$)")
_THEN_READ = re.compile(r"(?: and | then | ثم | و ?|, ?|; ?)(?:show|list|display|find|check|اعرض|اظهر|ابحث)(?: |$)")
_CONFIG_NOUN = re.compile(
    r"\b(?:custom )?fields?\b|\bworkflows?\b|\broles?\b|\bpermissions?\b|\btemplates?\b|\bsettings?\b|"
    r"\bconfig(?:uration)?\b|\bblueprint\b|\bapproval (?:steps?|stages?|workflows?|rules?|limits?|thresholds?|polic(?:y|ies)|chains?|levels?)\b|"
    r"\bnaming series\b|\bnumbering\b|\bnotification rules?\b|\bprint formats?\b|\bmodules?\b|"
    r"حقل|حقول|سير العمل|مسار العمل|صلاحي|ادوار|قالب|اعدادات|تهيئه|المخطط|بلوبرنت|حد الموافقه|قواعد? الموافقه")
_CONFIG_VERB = re.compile(r"^(?:enable|disable|turn (?:on|off)|switch (?:on|off)|configure|rename|require|فعل|عطل|وقف)(?: |$)")
_BUSINESS = re.compile(
    r"invoice|credit note|debit note|quot(?:e|ation)|\border\b|\bpo\b|purchase|customer|supplier|vendor|payment|voucher|"
    r"receipt|journal|asset|\breturn|opening balance|custody|iban|bank|\bitem\b|stock|expense|\bbill\b|payroll|"
    r"delivery|shipment|فاتوره|فواتير|اشعار|عرض سعر|امر |عميل|عملاء|مورد|دفع|سند|قيد|اصل|مرتجع|ايبان|عهده|صنف|مصروف|رصيد")
_DISCOVERY = re.compile(
    r"\b(?:we are an? |we're an? |i run |i own |my company|our company|my business|our business|we sell |we operate|"
    r"we have \d+ (?:staff|employees|people)|set up my|build (?:my|the|our) (?:erp|system|blueprint)|"
    r"start (?:the )?(?:interview|setup)|describe my business)|نشاطنا|شركتنا|نشاط شركتي|نحن شركه|عندنا \d+ موظف|"
    r"ابدا المقابله|ابغي انشئ نظام")
# A request that ends on a bare "the invoice" with no number or name does not say which record: ask first.
_BARE_REF = re.compile(r"(?:\b(?:the|this|that|it)(?: [a-z]+){0,2}|(?<!\w)(?:هذا |هذه )?ال(?:فاتوره|دفعه|امر|سند|عميل|مورد|قيد|اشعار))$")
_TIER = (("R4", re.compile(r"iban|ايبان|bank details|بيانات البنك|\bapprove|اعتمد|وافق|reject|ارفض|cancel[a-z]* .{0,20}(?:invoice|فاتوره)|"
                           r"الغ|امسح")),
         ("R3", re.compile(r"invoice|credit note|debit note|journal|payment|voucher|receipt|opening balance|custody|"
                           r"disburse|فاتوره|اشعار|قيد|سند|رصيد افتتاحي|عهده|دفع|صرف|قبض")),
         ("R2", re.compile(r"customer|\breturn|asset|مرتجع|ارجع|عميل|اصل ثابت|supplier|مورد")),
         ("R1", re.compile(r"quot|order|\bpo\b|purchase|عرض سعر|امر ")))
_CONFIG_RISK = re.compile(r"role|permission|approval|admin|صلاحي|ادوار|الموافقه")
# A grant, not a read: "give me the list of roles" and "make a report of every admin" are reads; "set the owner of
# invoice 5" changes a record, not a role.
_ROLE_GRANT = re.compile(
    r"^(?:(?:give|make|grant) (?!(?:me |us )?(?:a |an |the )?(?:list|report|summary|overview|count|total)\b).{0,40}"
    r"\b(?:roles?|admins?|administrators?|owner|permissions?)|set .{0,40}\b(?:roles?|permissions?)|"
    r"set .{0,40}\bas (?:an? |the )?(?:admin|administrator|owner))\b|"
    r"^(?:اعط|امنح|اجعل|خلي)\w* (?!(?:ال)?(?:قائمه|لائحه|تقرير|ملخص|عدد|اجمالي)).{0,40}(?:صلاحي|دور|ادمن|مدير|مالك)")
_BULK = re.compile(r"\b(?:all|every|each)\b|(?<!\w)كل(?!\w)|جميع")


@dataclass(frozen=True)
class RuleResult:
    mode: str | None              # None: no single mode (no signal, mixed or not a clear request)
    confidence: str = "low"
    reasons: frozenset = frozenset()
    explicit: bool = False        # imperative, desire or slash command (not a polite question)
    risk: str = "R0"
    meta: bool = False
    command: bool = False
    polite: bool = False


_ACT_BARE = re.compile(rf"^{_ACT_VERB}(?: |$)")


def _is_bare_ref(body: str, entity_names=()) -> bool:
    body = _FILLER.sub("", body)
    ent = any(e and re.search(rf"(?<!\w){re.escape(e)}(?!\w)", body) for e in (normalise(x) for x in entity_names))
    return (bool(_BUSINESS.search(body)) or ent) and not re.search(r"\d", body) and bool(_BARE_REF.search(body))


def strip_meta(t: str) -> tuple:
    clean = META.sub(" ", t)
    return re.sub(r"\s+", " ", clean).strip(), clean != t


def rule_risk(t: str, mode: str) -> str:
    if mode not in ("act", "change"):
        return "R0"
    if mode == "change":
        return "R3" if _CONFIG_RISK.search(t) or _ROLE_GRANT.match(SLASH.sub("", t, count=1)) else "R2"
    risks = [r for r, p in _TIER if p.search(t)]
    if _BULK.search(t):
        risks.append("R3")  # bulk wording never stays below R3
    return max_risk("R1", *risks)


def run_rules(turn, entity_names=(), blueprint_live: bool = True) -> RuleResult:
    t0 = normalise(turn)
    if not t0:
        return RuleResult(None, reasons=frozenset({"empty_input"}))
    t, meta = strip_meta(t0)
    reasons = {"meta_instruction"} if meta else set()
    m = SLASH.match(t0)
    if m:
        mode = _SLASH_MODE[m.group(1)]
        extra = {"slash_command"}
        body = SLASH.sub("", t, count=1)
        if mode in ("act", "change") and _ACT_BARE.match(body) and _is_bare_ref(body, entity_names):
            extra.add("ambiguous_reference")  # an explicit command still has to say which record
        return RuleResult(mode, "high", frozenset(reasons | extra), True, rule_risk(t, mode), meta, True)
    t = _FILLER.sub("", t)
    if not t:
        return RuleResult(None, reasons=frozenset(reasons | {"no_signal"}), meta=meta)
    entity = any(e and re.search(rf"(?<!\w){re.escape(e)}(?!\w)", t) for e in (normalise(x) for x in entity_names))
    if entity:
        reasons.add("entity_match")

    def done(mode, conf, extra, explicit=False, polite=False):
        r = frozenset(reasons | set(extra))
        return RuleResult(mode, conf, r, explicit, rule_risk(t, mode) if mode else "R0", meta, False, polite)

    config = bool(_CONFIG_NOUN.search(t))
    business = bool(_BUSINESS.search(t)) or entity
    if _POLITE.match(t):
        return done(None, "low", {"polite_request"}, polite=True)
    if _QUESTION.match(t) or "?" in t:
        return done("ask", "high", {"interrogative"})
    if _ROLE_GRANT.match(t):
        return done("change", "high", {"imperative_action", "config_object"}, True)
    if _READ.match(t):
        if _THEN_ACT.search(t):
            return done(None, "low", {"mixed_intent"})
        return done("ask", "high", {"read_verb"})
    if _DISCOVERY.search(t):
        return done("discover", "high", {"discovery_phrase"})
    if _IMPERATIVE.match(t):
        if _THEN_READ.search(t) or (config and business and _THEN_ACT.search(t)):
            return done(None, "low", {"mixed_intent"})
        if config:
            return done("change", "high", {"imperative_action", "config_object"}, True)
        desire = re.match(rf"^{_DESIRE} ", t) is not None
        if business and not re.search(r"\d", t) and _BARE_REF.search(t):  # a type name is not a record reference
            return done("act", "medium", {"imperative_action", "business_object", "ambiguous_reference"}, True)
        if business:
            return done("act", "high", {"desire_action" if desire else "imperative_action", "business_object"}, True)
        return done("act", "medium", {"desire_action" if desire else "imperative_action"}, True)
    if _CONFIG_VERB.match(t):
        return done("change", "high" if config else "medium", {"imperative_action"} | ({"config_object"} if config else set()), True)
    if _READ_OBJ.search(t) and not _ACT_ANYWHERE.search(t):
        return done("ask", "medium", {"read_verb"})
    if _ACT_ANYWHERE.search(t) and (config or business):
        return done(None, "low", {"mixed_intent"})  # a verb buried mid-sentence is not a command
    if not blueprint_live:
        return done("discover", "medium", {"discovery_phrase"})
    return done(None, "low", {"no_signal"})
