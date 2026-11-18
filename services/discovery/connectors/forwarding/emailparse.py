"""RFC822 parsing with the stdlib `email` package. Strings and bytes only: no network, no files.
Returns plain dicts. Attachment bytes stay in the returned `blobs` list, never in connector output."""
from __future__ import annotations

import datetime
import email
import email.policy
import re
from email.utils import getaddresses, parsedate_to_datetime
from html.parser import HTMLParser

from .common import clean, norm_line, sha, squash
from .errors import Fwd001NotAMessage, Fwd003TooManyParts, Fwd004Undecodable

MAX_PARTS = 60
MAX_PART_BYTES = 8_000_000
_SUBJ = re.compile(r"^\s*((re|fw|fwd|aw|sv|رد|إعادة توجيه|اعادة توجيه|تم التوجيه)\s*:\s*)+", re.I)
_HEADER_START = re.compile(rb"^[!-9;-~]{1,60}:[ \t]", re.M)
_HIDDEN = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0|opacity\s*:\s*0(?![.\d])", re.I)
_VOID = {"br", "hr", "img", "meta", "link", "input", "wbr"}


class _Text(HTMLParser):
    """HTML to text. Script and style are dropped; display:none text is kept apart as hidden text."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.vis, self.hid, self.stack = [], [], []

    def handle_starttag(self, tag, attrs):
        if tag in _VOID:
            if tag in ("br", "hr"):
                self.vis.append("\n")
            return
        style = " ".join(v or "" for k, v in attrs if k in ("style", "hidden", "aria-hidden"))
        hidden = tag in ("script", "style", "head", "template") or bool(_HIDDEN.search(style)) or \
            any(k == "hidden" for k, _ in attrs)
        self.stack.append((tag, hidden or (bool(self.stack) and self.stack[-1][1])))

    def handle_endtag(self, tag):
        while self.stack:
            t, _ = self.stack.pop()
            if t == tag:
                break
        if tag in ("p", "div", "tr", "li"):
            self.vis.append("\n")

    def handle_data(self, data):
        if self.stack and self.stack[-1][1]:
            if self.stack[-1][0] not in ("script", "style", "head", "template"):
                self.hid.append(data)
        else:
            self.vis.append(data)


def html_text(html: str) -> tuple:
    p = _Text()
    try:
        p.feed(html)
        p.close()
    except Exception:
        raise Fwd004Undecodable("html body")
    return "".join(p.vis), " ".join(x for x in p.hid if x.strip())


def _h(msg, name: str) -> str:
    try:
        v = msg.get(name)
        return squash(str(v)) if v is not None else ""
    except Exception:
        return ""


def _addrs(value: str) -> list:
    out = []
    for _, a in getaddresses([value]):
        a = a.strip().lower()
        if a and "@" in a:
            out.append(a)
    return out


def _date(value: str) -> tuple:
    """(iso, flags). A missing zone is flagged; an unparseable date is empty and flagged."""
    if not value:
        return "", ["date_missing"]
    try:
        d = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return "", ["date_unparseable"]
    flags = []
    if d.tzinfo is None:
        flags.append("timezone_unknown")
    elif d.tzinfo.utcoffset(d) == datetime.timedelta(0) and "-0000" in value:
        flags.append("timezone_unknown")
    return d.isoformat(), flags


def _decode(part) -> str:
    raw = part.get_payload(decode=True) or b""
    cs = part.get_content_charset() or "utf-8"
    try:
        return raw.decode(cs, "replace")
    except LookupError:
        return raw.decode("utf-8", "replace")


def split_quoted(text: str) -> tuple:
    """Split into (own text, quoted lines). Quoted lines start with '>'. Quoted lines that repeat the
    body are dropped (thread dedup inside one message)."""
    own, quoted = [], []
    for ln in text.splitlines():
        (quoted if ln.lstrip().startswith(">") else own).append(ln)
    seen = {norm_line(x) for x in own if x.strip()}
    q, dropped = [], 0
    for ln in quoted:
        body = ln.lstrip().lstrip("> ").strip()
        k = norm_line(body)
        if not k:
            continue
        if k in seen:
            dropped += 1
            continue
        seen.add(k)
        q.append(body)
    return "\n".join(own).strip(), "\n".join(q), dropped


def parse_email(source: bytes) -> dict:
    if not _HEADER_START.match(source.lstrip()[:2000] or b""):
        raise Fwd001NotAMessage("no header block")
    try:
        msg = email.message_from_bytes(source, policy=email.policy.default)
    except Exception:
        raise Fwd001NotAMessage("unparseable")
    if not (msg.get("From") or msg.get("Date") or msg.get("Message-ID")):
        raise Fwd001NotAMessage("no From, Date or Message-ID")
    date_iso, dflags = _date(_h(msg, "Date"))
    plain, html, atts, blobs, n = [], [], [], [], 0
    for part in msg.walk():
        n += 1
        if n > MAX_PARTS:
            raise Fwd003TooManyParts(f"more than {MAX_PARTS} parts")
        if part.is_multipart():
            continue
        ctype, fname = part.get_content_type(), part.get_filename()
        is_att = fname is not None or part.get_content_disposition() == "attachment" or \
            not ctype.startswith("text/")
        if not is_att and ctype == "text/plain":
            plain.append(_decode(part))
        elif not is_att and ctype == "text/html":
            html.append(_decode(part))
        else:
            data = part.get_payload(decode=True) if ctype != "message/rfc822" else part.as_bytes()
            data = data or b""
            if len(data) > MAX_PART_BYTES:
                raise Fwd003TooManyParts("attachment over size cap")
            atts.append({"name": fname or "", "declared": ctype, "size": len(data), "sha256": sha(data),
                         "nested_message": ctype == "message/rfc822"})
            blobs.append(data)
    hidden = ""
    if plain:
        body = "\n".join(plain)
    else:
        body, hidden = html_text("\n".join(html)) if html else ("", "")
    own, quoted, dropped = split_quoted(body)
    refs = [r for r in re.findall(r"<[^<>\s]+>", _h(msg, "References"))]
    mid = _h(msg, "Message-ID")
    irt = _h(msg, "In-Reply-To")
    subj_key = norm_line(_SUBJ.sub("", _h(msg, "Subject")))
    root = refs[0] if refs else (irt or mid or "")
    thread = sha((root or f"subj:{subj_key}").lower().encode())[:16]
    frm = _addrs(_h(msg, "From"))
    content_key = sha("\n".join([",".join(frm), subj_key, "\n".join(norm_line(x) for x in own.splitlines())])
                      .encode())[:32]
    return {
        "from": frm, "from_count": len(frm), "reply_to": _addrs(_h(msg, "Reply-To")),
        "to": _addrs(_h(msg, "To")), "cc": _addrs(_h(msg, "Cc")), "subject": _h(msg, "Subject"),
        "date": date_iso, "date_flags": dflags, "message_id": mid, "in_reply_to": irt, "thread": thread,
        "content_key": content_key, "body": own, "quoted": quoted, "quoted_dropped": dropped,
        "hidden_body": hidden, "attachments": atts, "blobs": blobs, "html_only": not plain and bool(html),
    }


def thread_key(source: bytes) -> tuple:
    """(thread id, content key) for dedup across forwarded copies."""
    p = parse_email(source)
    return p["thread"], p["content_key"]


def dedupe_messages(sources: list) -> tuple:
    """Keep the first of each duplicate (same Message-ID, or same sender, subject and body).
    Returns (kept sources, number dropped). Unparseable items are kept for the connector to refuse."""
    seen, kept, dropped = set(), [], 0
    for s in sources:
        try:
            p = parse_email(s)
        except Exception:
            kept.append(s)
            continue
        keys = {("c", p["content_key"])} | ({("m", p["message_id"].lower())} if p["message_id"] else set())
        if keys & seen:
            dropped += 1
            continue
        seen |= keys
        kept.append(s)
    return kept, dropped
