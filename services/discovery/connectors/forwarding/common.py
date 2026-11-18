"""Shared pure helpers: control stripping before parsing, dates (Gregorian and Hijri), hashing."""
from __future__ import annotations

import hashlib
import re

from ..intake.parse import find_dates, fold
from ..sanitise import strip_controls

_WS = re.compile(r"[ \t ]+")
_NONWORD = re.compile(r"[\W_]+", re.UNICODE)


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def clean(text: str) -> str:
    """Control-stripped copy used only for parsing. The original text still goes to the runner so
    the bidi and invisible-character flags are raised there."""
    return strip_controls(text)[0]


def norm_line(s: str) -> str:
    """Dedup key for a line: stripped, digits and alef forms folded, punctuation and case dropped."""
    return _NONWORD.sub(" ", fold(clean(s))).strip()


def dates_in(text: str, cap: int = 20) -> list:
    """Dates found in text as [{"iso","calendar","flags"}]; Hijri is converted with Umm al-Qura
    (DSC-014 helper). Every result is a comparison copy of a stated date, never a fact."""
    out = []
    for line in clean(text).splitlines():
        for d in find_dates(fold(line)):
            out.append({"iso": d["iso"], "calendar": d["calendar"], "flags": list(d["flags"])})
            if len(out) >= cap:
                return out
    return out


def squash(s: str) -> str:
    return _WS.sub(" ", s).strip()
