"""QA-015 property tests for date handling. Deterministic: no model calls, seeded random loops, stdlib plus hijridate and zoneinfo.

Production code covered: connectors.intake.parse (hijri_to_gregorian, find_dates, fold) and the pinned hijridate tables (CMP-022).
Not implemented anywhere in the repo yet, so a tiny reference helper in this file encodes the rule from
docs/architecture/calendars-and-locale.md: weekend defaults per market, Hijri fiscal year boundaries, local date from UTC.
Every rule the doc marks UNVERIFIED is an xfail with that reason; rules the doc leaves undefined (week start day per market,
Qatar weekend) are not asserted and are recorded in docs/open-questions.md. The tz database must be installed (tzdata)."""
import calendar
import datetime as dt
import random

import pytest
from hijridate import Gregorian, Hijri

from connectors.intake.parse import find_dates, fold, hijri_to_gregorian

try:
    from zoneinfo import ZoneInfo
    TZ = {n: ZoneInfo(n) for n in ("Asia/Riyadh", "Asia/Dubai", "Africa/Cairo", "Asia/Qatar")}
except Exception as exc:
    raise RuntimeError("QA-015 needs the IANA tz database: install the tzdata package (uv run --with tzdata). " + repr(exc))

SEED = 20261118
FIRST_AH, LAST_AH = 1343, 1500


def month_len(y, m):
    """Umm al-Qura month length from the tables: distance to the first of the next month."""
    ny, nm = (y, m + 1) if m < 12 else (y + 1, 1)
    return (Hijri(ny, nm, 1).to_gregorian() - Hijri(y, m, 1).to_gregorian()).days


def all_months():
    for y in range(FIRST_AH, LAST_AH + 1):
        for m in range(1, 13):
            if (y, m) != (LAST_AH, 12):
                yield y, m


# --- Hijri conversion ---------------------------------------------------------------------------
def test_hijri_roundtrip_every_month_start_and_random_days():
    rnd = random.Random(SEED)
    for y, m in all_months():
        n = month_len(y, m)
        for d in {1, n, rnd.randint(1, n)}:
            g = hijri_to_gregorian(y, m, d)
            h = Gregorian(g.year, g.month, g.day).to_hijri()
            assert (h.year, h.month, h.day) == (y, m, d)


def test_gregorian_to_hijri_to_gregorian_roundtrip_seeded():
    rnd = random.Random(SEED + 1)
    lo, hi = dt.date(1924, 8, 1), dt.date(2077, 11, 15)
    for _ in range(3000):
        g = lo + dt.timedelta(days=rnd.randint(0, (hi - lo).days))
        h = Gregorian(g.year, g.month, g.day).to_hijri()
        assert hijri_to_gregorian(h.year, h.month, h.day) == g


LEGACY_ODD_MONTHS = {(1343, 9): 28, (1345, 5): 31, (1345, 8): 28, (1348, 11): 31, (1348, 12): 28,
                     (1349, 10): 28, (1349, 11): 31, (1364, 8): 28}


def test_hijri_month_lengths_29_or_30_from_1365_and_pinned_odd_months_before():
    odd = {}
    for y, m in all_months():
        n = month_len(y, m)
        if n not in (29, 30):
            odd[(y, m)] = n
    assert odd == LEGACY_ODD_MONTHS
    assert all(y < 1365 for y, _ in odd)
    for y in range(FIRST_AH, LAST_AH):
        days = (Hijri(y + 1, 1, 1).to_gregorian() - Hijri(y, 1, 1).to_gregorian()).days
        assert 353 <= days <= 356, (y, days)


def test_hijri_day_limits_refused():
    for y, m in all_months():
        n = month_len(y, m)
        assert hijri_to_gregorian(y, m, n)
        with pytest.raises(ValueError):
            hijri_to_gregorian(y, m, n + 1)
    for bad in ((1400, 1, 0), (1400, 1, 31), (1400, 0, 1), (1400, 13, 1)):
        with pytest.raises(ValueError):
            hijri_to_gregorian(*bad)


def test_hijri_monotonic_and_contiguous():
    prev = None
    for y, m in all_months():
        for d in (1, month_len(y, m)):
            g = hijri_to_gregorian(y, m, d)
            if prev is not None:
                assert g > prev
            prev = g
        assert hijri_to_gregorian(y, m, month_len(y, m)) + dt.timedelta(days=1) == (
            hijri_to_gregorian(y, m + 1, 1) if m < 12 else hijri_to_gregorian(y + 1, 1, 1))


@pytest.mark.parametrize("y", [0, 1, 1342, 1501, 1600, 2024, -5])
def test_hijri_out_of_range_year_refused(y):
    with pytest.raises(ValueError):
        hijri_to_gregorian(y, 1, 1)


def test_table_edges():
    assert hijri_to_gregorian(1343, 1, 1) == dt.date(1924, 8, 1)
    assert hijri_to_gregorian(1500, 12, 29) == dt.date(2077, 11, 15)


# --- Gregorian ----------------------------------------------------------------------------------
def test_gregorian_leap_years_and_month_ends():
    for y in range(1900, 2101):
        leap = y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)
        assert calendar.isleap(y) == leap
        assert calendar.monthrange(y, 2)[1] == (29 if leap else 28)
        for m in range(1, 13):
            last = dt.date(y, m, calendar.monthrange(y, m)[1])
            assert (last + dt.timedelta(days=1)).day == 1
            assert (last + dt.timedelta(days=1)).month == (m % 12) + 1
    assert find_dates("2024-02-29")[0]["iso"] == "2024-02-29"
    assert find_dates("2023-02-29") == [] and find_dates("2100-02-29") == [] and find_dates("2024-04-31") == []


# --- parsing ------------------------------------------------------------------------------------
def test_ambiguous_day_month_flagged_only_when_ambiguous():
    for text, flagged in (("03/04/2024", True), ("13/04/2024", False), ("05/05/2024", False), ("04/13/2024", False)):
        ds = find_dates(text)
        if ds:
            assert ("ambiguous_day_month" in ds[0]["flags"]) is flagged, text
    assert find_dates("03/04/2024")[0]["iso"] == "2024-04-03"
    assert find_dates("2024-04-03")[0]["flags"] == []


def test_digit_sets_give_the_same_date():
    arabic_indic, persian = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩"), str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
    rnd = random.Random(SEED + 2)
    for _ in range(300):
        y, m, d = rnd.randint(1925, 2076), rnd.randint(1, 12), rnd.randint(1, 28)
        for text in (f"{y}-{m:02d}-{d:02d}", f"{d:02d}/{m:02d}/{y}"):
            base = find_dates(fold(text))
            assert base
            for tr in (arabic_indic, persian):
                assert find_dates(fold(text.translate(tr))) == base
    for y, m, d in ((1446, 3, 15), (1400, 12, 29), (1343, 1, 1)):
        text = f"{y}/{m:02d}/{d:02d}"
        want = find_dates(text)
        assert want and want[0]["calendar"] == "hijri"
        assert find_dates(fold(text.translate(arabic_indic))) == want
        assert find_dates(fold(text.translate(persian))) == want


def test_hijri_range_disambiguation_and_refusal():
    assert find_dates("1446/03/15")[0]["calendar"] == "hijri"
    assert find_dates("2024/03/15")[0]["calendar"] == "gregorian"
    assert find_dates("1501/01/01") == [] and find_dates("1342/01/01") == []


# --- week, weekend, fiscal (reference helpers; doc rules) ---------------------------------------
FRI, SAT, SUN = 4, 5, 6  # datetime.weekday()
DOC_WEEKENDS = {"SA": {FRI, SAT}, "AE": {SAT, SUN}, "EG": {FRI, SAT}}


def is_weekend(country, d, weekend=None):
    return d.weekday() in (weekend if weekend is not None else DOC_WEEKENDS[country])


def next_working_day(country, d, weekend=None):
    d += dt.timedelta(days=1)
    while is_weekend(country, d, weekend):
        d += dt.timedelta(days=1)
    return d


def hijri_fiscal_year(ah_year, start_month=1, start_day=1):
    """Doc rule: a Hijri fiscal year is a Hijri start rule mapped to Gregorian start and end, stored as explicit period rows."""
    start = hijri_to_gregorian(ah_year, start_month, start_day)
    nxt = hijri_to_gregorian(ah_year + 1, start_month, start_day)
    return start, nxt - dt.timedelta(days=1)


def gregorian_fiscal_year(y, start_month=1):
    start = dt.date(y, start_month, 1)
    return start, dt.date(y + 1, start_month, 1) - dt.timedelta(days=1)


def test_company_weekend_override_changes_working_days():
    fri = dt.date(2026, 11, 20)
    assert fri.weekday() == FRI
    assert next_working_day("SA", dt.date(2026, 11, 19)) == dt.date(2026, 11, 22)
    assert next_working_day("SA", dt.date(2026, 11, 19), weekend={SAT, SUN}) == fri


@pytest.mark.xfail(reason="weekend defaults are UNVERIFIED in the doc (confirm per pack): KSA Fri-Sat, UAE Sat-Sun, Egypt Fri-Sat", strict=False)
@pytest.mark.parametrize("country,days", [("SA", {4, 5}), ("AE", {5, 6}), ("EG", {4, 5})])
def test_market_weekend_defaults(country, days):
    assert DOC_WEEKENDS[country] == days
    pytest.xfail("UNVERIFIED in docs/architecture/calendars-and-locale.md")


@pytest.mark.xfail(reason="week start per market and the Qatar weekend are not stated in the doc (open question), nothing to assert", strict=True)
def test_week_start_per_market_undefined():
    pytest.fail("calendars-and-locale.md names only `locale.week.startDay`; no default per market")


def test_hijri_fiscal_years_tile_without_gap_or_overlap():
    for start_month, start_day in ((1, 1), (9, 1), (12, 28)):
        prev_end = None
        for y in range(FIRST_AH, LAST_AH):
            s, e = hijri_fiscal_year(y, start_month, start_day)
            assert s <= e and 353 <= (e - s).days + 1 <= 356
            if prev_end is not None:
                assert s == prev_end + dt.timedelta(days=1)
            prev_end = e


def test_gregorian_fiscal_year_boundaries_and_leap():
    for y in range(1990, 2100):
        s, e = gregorian_fiscal_year(y)
        assert (s, e) == (dt.date(y, 1, 1), dt.date(y, 12, 31))
        assert (e - s).days + 1 == (366 if calendar.isleap(y) else 365)
        s2, e2 = gregorian_fiscal_year(y, 7)
        assert (e2 - s2).days + 1 == (366 if calendar.isleap(y + 1) else 365) and e2.month == 6


# --- time zones ---------------------------------------------------------------------------------
def local_date(utc, zone):
    return utc.astimezone(TZ[zone]).date()


def test_fixed_offset_zones_have_constant_offset_all_year():
    year = [dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc) + dt.timedelta(days=d) for d in range(0, 365, 7)]
    for name in ("Asia/Riyadh", "Asia/Dubai", "Asia/Qatar"):
        assert len({t.astimezone(TZ[name]).utcoffset() for t in year}) == 1, name
    off = lambda n: year[0].astimezone(TZ[n]).utcoffset()
    assert off("Asia/Riyadh") == dt.timedelta(hours=3) and off("Asia/Qatar") == dt.timedelta(hours=3)
    assert off("Asia/Dubai") == dt.timedelta(hours=4)


def test_cairo_offset_is_what_zoneinfo_returns_and_stays_in_range():
    offs = {dt.datetime(y, m, 15, 12, tzinfo=dt.timezone.utc).astimezone(TZ["Africa/Cairo"]).utcoffset()
            for y in range(2020, 2031) for m in range(1, 13)}
    assert offs <= {dt.timedelta(hours=2), dt.timedelta(hours=3)} and dt.timedelta(hours=2) in offs


def test_utc_to_local_date_at_midnight_and_roundtrip():
    rnd = random.Random(SEED + 3)
    for name, tz in TZ.items():
        base = dt.datetime(2026, 11, 17, 12, tzinfo=dt.timezone.utc).astimezone(tz).utcoffset()
        edge = dt.datetime(2026, 11, 17, 0, 0, tzinfo=tz).astimezone(dt.timezone.utc)
        assert local_date(edge, name) == dt.date(2026, 11, 17)
        assert local_date(edge - dt.timedelta(seconds=1), name) == dt.date(2026, 11, 16)
        assert edge.replace(tzinfo=None) == dt.datetime(2026, 11, 17) - base
        for _ in range(200):
            u = dt.datetime(2020, 1, 1, tzinfo=dt.timezone.utc) + dt.timedelta(seconds=rnd.randint(0, 10 * 365 * 86400))
            loc = u.astimezone(tz)
            assert loc.astimezone(dt.timezone.utc) == u and loc.date() == local_date(u, name)
    late = dt.datetime(2026, 11, 17, 21, 30, tzinfo=dt.timezone.utc)
    assert local_date(late, "Asia/Riyadh") == dt.date(2026, 11, 18) and late.date() == dt.date(2026, 11, 17)


@pytest.mark.xfail(reason="Egypt daylight saving since 2023 is UNVERIFIED in the doc; transition dates depend on the installed tz database", strict=False)
def test_cairo_summer_offset_plus_three():
    summer = dt.datetime(2026, 7, 1, 12, tzinfo=dt.timezone.utc).astimezone(TZ["Africa/Cairo"])
    assert summer.utcoffset() == dt.timedelta(hours=3)
    pytest.xfail("UNVERIFIED in docs/architecture/calendars-and-locale.md")
