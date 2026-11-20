"""Price book: a data file of prices in integer minor units, validated strictly (it is untrusted input).

The shipped `price_book.placeholder.json` holds PLACEHOLDER values (UNVERIFIED). Real prices are a founder decision
(docs/strategy/07-pricing.md says every number is a hypothesis); nothing here is a price we offer.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

from .errors import QuoteError
from .money import EXPONENT, MAX_MINOR, is_int

SCHEMA = "price-book/0.1.0"
MAX_PRICE = 10 ** 12
MAX_COUNT = 10 ** 9
MAX_VALIDITY_DAYS = 90
_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")
_CID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_CC = re.compile(r"^[A-Z]{2}$")
TOP = {"schema", "id", "status", "validity_days", "markets", "currencies"}
CUR = {"base_platform_monthly", "module_default_monthly", "configuration_one_off", "build_one_off", "allowances", "components"}
ALLOW = {"ai_actions_monthly", "overage_pack_size", "overage_pack_price"}


MARKET_CURRENCY = {"SA": "SAR", "AE": "AED", "EG": "EGP", "QA": "QAR"}  # phase-1 markets; a mismatch needs `currency_override`
_MAX_DEPTH = 64


def _strict(obj, depth=0):
    """Only JSON types, string keys, finite numbers, bounded depth: otherwise two different objects could share a digest."""
    if depth > _MAX_DEPTH:
        raise ValueError("depth")
    if obj is None or isinstance(obj, (bool, str)) or (isinstance(obj, int)):
        return
    if isinstance(obj, float):
        if not math.isfinite(obj):
            raise ValueError("non-finite")
        return
    if isinstance(obj, list):
        for x in obj:
            _strict(x, depth + 1)
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            if not isinstance(k, str):
                raise ValueError("key")
            _strict(v, depth + 1)
        return
    raise ValueError("type")


def canonical(obj) -> bytes:
    try:
        _strict(obj)
        return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, ValueError, RecursionError):
        raise QuoteError("QTE-JSON-001", "not plain JSON (string keys, finite numbers, bounded depth)") from None


def digest(obj) -> str:
    return hashlib.sha256(canonical(obj)).hexdigest()


def _bad(detail: str):
    raise QuoteError("QTE-PB-001", detail)


def _keys(d, want: set, where: str):
    if not isinstance(d, dict) or set(d) != want:
        _bad(f"{where}: keys must be exactly {sorted(want)}")


def _num(v, where: str, lo=0, hi=MAX_PRICE):
    if not is_int(v) or not lo <= v <= hi:
        _bad(f"{where}: integer {lo}..{hi} required")
    return v


def _no_dups(pairs):
    d = {}
    for k, v in pairs:
        if k in d:
            raise QuoteError("QTE-PB-001", f"duplicate key {k[:40]!r}")
        d[k] = v
    return d


def _no_const(name):
    raise QuoteError("QTE-PB-001", f"non-finite number {name}")


def load_price_book(path) -> dict:
    """Read and validate a price book file. Duplicate keys, NaN and Infinity are refused."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=_no_dups, parse_constant=_no_const)
    except (OSError, ValueError) as e:
        if isinstance(e, QuoteError):
            raise
        raise QuoteError("QTE-PB-001", "unreadable or not JSON") from None
    return validate_price_book(raw)


def default_price_book() -> dict:
    return load_price_book(Path(__file__).with_name("price_book.placeholder.json"))


def validate_price_book(pb) -> dict:
    """Return pb unchanged when valid, else raise QTE-PB-001. Unknown keys, floats, bools, negatives, oversized
    numbers, odd identifiers and a market whose currency has no price table are all refused."""
    _keys(pb, TOP, "price book")
    if pb["schema"] != SCHEMA:
        _bad("schema")
    if not isinstance(pb["id"], str) or not _ID.fullmatch(pb["id"]):
        _bad("id")
    if not isinstance(pb["status"], str) or pb["status"] not in ("placeholder", "approved"):
        _bad("status")
    _num(pb["validity_days"], "validity_days", 1, MAX_VALIDITY_DAYS)
    if not isinstance(pb["markets"], dict) or not 0 < len(pb["markets"]) <= 50:
        _bad("markets")
    if not isinstance(pb["currencies"], dict) or not 0 < len(pb["currencies"]) <= 20:
        _bad("currencies")
    for cc, m in pb["markets"].items():
        if not isinstance(cc, str) or not _CC.fullmatch(cc):
            _bad("market key")
        if isinstance(m, dict) and set(m) == {"currency", "tax", "currency_override"}:
            if m["currency_override"] is not True:
                _bad(f"market {cc}: currency_override")
        else:
            _keys(m, {"currency", "tax"}, f"market {cc}")
        if not isinstance(m["currency"], str) or m["currency"] not in pb["currencies"] or m["currency"] not in EXPONENT:
            _bad(f"market {cc}: currency")
        if cc in MARKET_CURRENCY and m["currency"] != MARKET_CURRENCY[cc] and "currency_override" not in m:
            _bad(f"market {cc}: currency must be {MARKET_CURRENCY[cc]} unless currency_override is true")
        _keys(m["tax"], {"rate_bp"}, f"market {cc} tax")
        _num(m["tax"]["rate_bp"], f"market {cc} tax rate_bp", 0, 10000)
    for cur, c in pb["currencies"].items():
        if cur not in EXPONENT:
            _bad("currency")
        _keys(c, CUR, f"currency {cur}")
        for k in ("base_platform_monthly", "module_default_monthly", "configuration_one_off"):
            _num(c[k], f"{cur}.{k}")
        _keys(c["build_one_off"], {"configurable", "rigid"}, f"{cur}.build_one_off")
        for k, v in c["build_one_off"].items():
            _num(v, f"{cur}.build_one_off.{k}")
        _keys(c["allowances"], ALLOW, f"{cur}.allowances")
        _num(c["allowances"]["ai_actions_monthly"], "ai_actions_monthly", 0, MAX_COUNT)
        _num(c["allowances"]["overage_pack_size"], "overage_pack_size", 1, MAX_COUNT)
        _num(c["allowances"]["overage_pack_price"], "overage_pack_price")
        if not isinstance(c["components"], dict) or len(c["components"]) > 5000:
            _bad(f"{cur}.components")
        for cid, v in c["components"].items():
            if not isinstance(cid, str) or not _CID.fullmatch(cid):
                _bad(f"{cur}.components id")
            _num(v, f"{cur}.components.{cid[:40]}")
    assert MAX_PRICE < MAX_MINOR
    return pb
