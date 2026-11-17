"""DSC-014 parsing helpers: amounts, separators, dates, Hijri conversion are pure and deterministic."""
import datetime
from decimal import Decimal

import pytest

from connectors.intake.parse import find_currency, find_dates, fold, hijri_to_gregorian, parse_amount


@pytest.mark.parametrize("raw,val,amb", [
    ("1,234.50", "1234.50", False), ("١٢٣٤٫٥٠", "1234.50", False), ("1.234,50", "1234.50", False),
    ("1٬234٫5", "1234.5", False), ("12,50", "12.50", False), ("1,234", "1234", True),
    ("1,234,567", "1234567", False), ("100", "100", False), ("۱۲٫۵", "12.5", False),
])
def test_parse_amount(raw, val, amb):
    assert parse_amount(fold(raw)) == (Decimal(val), amb)


def test_parse_amount_rejects_garbage():
    assert parse_amount("1,23,4")[0] is None and parse_amount("...")[0] is None


def test_hijri_conversion_known_pairs_within_a_day():
    # Umm al-Qura: 1 Ramadan 1445 = 2024-03-11, 1 Muharram 1446 = 2024-07-07. The civil table can differ by a day.
    for (y, m, d), want in (((1445, 9, 1), datetime.date(2024, 3, 11)), ((1446, 1, 1), datetime.date(2024, 7, 7))):
        assert abs((hijri_to_gregorian(y, m, d) - want).days) <= 1
    assert hijri_to_gregorian(1446, 1, 1) == hijri_to_gregorian(1446, 1, 1)


def test_find_dates_calendars_and_invalid():
    ds = find_dates(fold("١٤٤٦/٠٣/١٥هـ الموافق ٢٠٢٤-٠٩-١٨"))
    assert [d["calendar"] for d in ds] == ["hijri", "gregorian"] and ds[1]["iso"] == "2024-09-18"
    assert find_dates("2024-13-45") == [] and find_dates("1700/01/01") == []
    d = find_dates("25/12/2024")[0]
    assert d["iso"] == "2024-12-25" and d["flags"] == []


def test_currency_none_when_absent():
    assert find_currency(fold("no money here")) is None
