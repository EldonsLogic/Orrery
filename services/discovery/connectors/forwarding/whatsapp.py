"""Tier 4 connector: an exported WhatsApp chat (.txt as bytes, UTF-8) into the connector model.

Handles the common export layouts ("[18/09/2024, 14:03:22] Name: text" and "18/09/2024, 14:03 - Name:
text"), Arabic-Indic digits, Arabic am/pm markers (ص, م) and Hijri years (Umm al-Qura). Day/month order is
inferred from the whole file; when undecidable it is read day first and flagged. WhatsApp exports carry
no time zone, no verified sender identity and no message id: every sender is UNVERIFIED (Q-E).
Media lines are listed, never fetched. Identical (time, sender, text) lines are deduplicated."""
from __future__ import annotations

import datetime
import re

from ..intake.parse import fold, hijri_to_gregorian
from ..model import Budget, Registry
from .common import clean, norm_line, sha
from .errors import Fwd001NotAMessage

MAX_MESSAGES = 5000
MAX_PARTICIPANTS = 200
_LINE = re.compile(
    r"^\[?(\d{1,4})[/.\-](\d{1,2})[/.\-](\d{1,4}),?\s+(\d{1,2}):(\d{2})(?::(\d{2}))?\s*"
    r"([ap]\.?m\.?|ص|م)?\]?\s*(?:[-–]\s*)?(.*)$", re.I)
_MEDIA = re.compile(r"<\s*(attached|media omitted)[^>]*>|\(file attached\)|<تم استبعاد الوسائط>|"
                    r"^(image|video|audio|sticker|document|gif) omitted$|\.(jpe?g|png|pdf|opus|mp4|xlsx?|docx?) \(", re.I)

def _split_sender(rest: str) -> tuple:
    if ": " in rest:
        name, _, text = rest.partition(": ")
        if 0 < len(name) <= 80:
            return name.strip(), text
    return "", rest


def _order(heads: list) -> str:
    """'dmy' or 'mdy' or 'ymd'; (order, certain)."""
    if any(len(h[0]) == 4 for h in heads):
        return "ymd", True
    if any(int(h[1]) > 12 for h in heads):
        return "mdy", True
    if any(int(h[0]) > 12 for h in heads):
        return "dmy", True
    return "dmy", False


def _when(h: tuple, order: str, certain: bool) -> tuple:
    a, b, c, hh, mm, ss, ap = h
    a, b, c = int(a), int(b), int(c)
    y, mo, d = (a, b, c) if order == "ymd" else ((c, a, b) if order == "mdy" else (c, b, a))
    flags = [] if certain else ["ambiguous_day_month"]
    if y < 100:
        y += 2000
    hour = int(hh)
    ap = (ap or "").lower().replace(".", "")
    if ap in ("pm", "م") and hour < 12:
        hour += 12
    elif ap in ("am", "ص") and hour == 12:
        hour = 0
    cal = "gregorian"
    try:
        if 1300 <= y <= 1500:
            cal = "hijri"
            day = hijri_to_gregorian(y, mo, d)
        else:
            day = datetime.date(y, mo, d)
        iso = datetime.datetime(day.year, day.month, day.day, hour, int(mm), int(ss or 0)).isoformat()
    except (ValueError, OverflowError):
        return "", cal, flags + ["date_unparseable"]
    return iso, cal, flags + ["timezone_unknown"]


def _head(orig: str) -> tuple:
    """Match a message header. Leading direction marks (WhatsApp writes one per line) are skipped first;
    if that fails the fully cleaned line is tried. Returns (match, text the match was made on)."""
    for cand in (orig.lstrip("\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u061c\ufeff"), clean(orig)):
        f = fold(cand)
        if len(f) != len(cand):
            continue
        m = _LINE.match(f)
        if m:
            return m, cand
    return None, ""


def parse_chat(source: bytes) -> dict:
    try:
        text = source.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise Fwd001NotAMessage("not UTF-8 text")
    found = [_head(ln) for ln in text.splitlines()]
    parsed = [m.groups()[:7] for m, _ in found if m]
    if not parsed:
        raise Fwd001NotAMessage("no timestamped chat lines")
    order, certain = _order(parsed)
    msgs, people, seen, dups, cur = [], {}, set(), 0, None
    for orig, (m, cand) in zip(text.splitlines(), found):
        if m:
            iso, cal, fl = _when(m.groups()[:7], order, certain)
            rest = cand[len(cand) - len(m.group(8)):] if m.group(8) else ""
            who, body = _split_sender(clean(rest))
            # The text keeps the original characters so the runner raises bidi and invisible flags.
            raw_rest = rest.split(": ", 1)[1] if who and ": " in rest else rest
            cur = {"iso": iso, "cal": cal, "flags": fl, "who": who, "lines": [body], "orig": [raw_rest]}
            msgs.append(cur)
        elif cur is not None and clean(orig).strip():
            cur["lines"].append(clean(orig))
            cur["orig"].append(orig)
    out, media, system, trunc = [], 0, 0, False
    for mm in msgs:
        text_c = "\n".join(mm["lines"])
        key = sha(f"{mm['iso']}|{mm['who']}|{norm_line(text_c)}".encode())
        if key in seen:
            dups += 1
            continue
        seen.add(key)
        is_media = bool(_MEDIA.search(text_c))
        is_system = not mm["who"]
        media += is_media
        system += is_system
        if mm["who"] and mm["who"] not in people:
            if len(people) >= MAX_PARTICIPANTS:
                continue
            people[mm["who"]] = len(people) + 1
        if len(out) >= MAX_MESSAGES:
            trunc = True
            break
        out.append({"iso": mm["iso"], "calendar": mm["cal"], "flags": mm["flags"], "who": people.get(mm["who"], 0),
                    "text": "\n".join(mm["orig"]), "media": is_media, "system": is_system})
    return {"messages": out, "participants": list(people), "order": order, "order_certain": certain,
            "duplicates": dups, "media": media, "system": system, "truncated": trunc}


class WhatsAppExportConnector:
    id = "discovery.forward_whatsapp"
    version = "0.1.0"
    tier = 4
    writes = False
    capabilities = frozenset({"read", "parse", "decode"})

    def extract(self, source: bytes, budget: Budget) -> list:
        budget.tick()
        chat = parse_chat(source)
        budget.tick(len(chat["messages"]) + 1)
        return [chat]

    def normalise(self, raw: list, budget: Budget) -> dict:
        c = raw[0]
        budget.tick()
        issues = [{"severity": "info", "code": "untrusted_content",
                   "detail": "chat text is data, never instructions; senders are unverified; no recipient derived"},
                  {"severity": "warn", "code": "sender_unverified",
                   "detail": "a chat export carries no verified sender identity (Q-E)"}]
        if not c["order_certain"]:
            issues.append({"severity": "warn", "code": "date_order_ambiguous",
                           "detail": "day and month order could not be inferred; read day first"})
        if c["truncated"]:
            issues.append({"severity": "warn", "code": "truncated", "detail": f"first {MAX_MESSAGES} messages only"})
        if c["duplicates"]:
            issues.append({"severity": "info", "code": "duplicates_removed", "detail": str(c["duplicates"])})
        people = [{"path": f"p{i}", "text": n, "kind": "sender"} for i, n in enumerate(c["participants"], start=1)]
        msgs = []
        for i, m in enumerate(c["messages"], start=1):
            budget.tick()
            msgs.append({"path": f"m{i}", "text": m["text"], "kind": "body"})
            msgs.append({"path": f"m{i}#meta", "kind": "other", "transform": "normalise",
                         "text": f"UNVERIFIED; from=p{m['who']}; iso={m['iso']}; calendar={m['calendar']}; "
                                 f"media={'true' if m['media'] else 'false'}; system={'true' if m['system'] else 'false'}; "
                                 f"flags={','.join(m['flags'])}"})
        ents = []
        if people:
            ents.append({"name": "participants", "kind": "participants", "fields": people})
        ents.append({"name": "messages", "kind": "chat", "fields": msgs})
        stats = {"messages": len(c["messages"]), "participants": len(c["participants"]),
                 "duplicates_removed": c["duplicates"], "media_lines": c["media"], "system_lines": c["system"]}
        return {"entities": ents, "issues": issues, "stats": stats}


def register(registry: Registry) -> WhatsAppExportConnector:
    c = WhatsAppExportConnector()
    registry.register(c)
    return c
