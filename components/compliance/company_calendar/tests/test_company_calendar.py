"""Tests for per-company calendar and week settings (CMP-023). Packs are read only through the public API."""

from __future__ import annotations

import ast
import copy
import dataclasses
from datetime import date, datetime, time
from importlib import metadata
from pathlib import Path
import pickle
import re
import unittest

from components.compliance.company_calendar import (
    CalendarSettingsError,
    resolve_calendar_settings,
)
from components.compliance.country_pack import (
    CountryPackError,
    OverrideRejectedError,
    PackValidationError,
    UnknownCountryError,
)

PACKS_DIR = Path(__file__).resolve().parents[2] / "country_pack" / "packs"
REPO_ROOT = Path(__file__).resolve().parents[4]


def resolve(country: str, overrides=None, **kw):
    kw.setdefault("environment", "test")
    return resolve_calendar_settings(country, PACKS_DIR, overrides, version="0.1.0", **kw)


class TestDefaultsFromPack(unittest.TestCase):
    def test_sa_defaults(self) -> None:
        s = resolve("SA")
        self.assertEqual(s.country_code, "SA")
        self.assertEqual(s.week_start, "sun")
        self.assertEqual(s.weekend_days, ("fri", "sat"))
        self.assertEqual(s.work_days, ("sun", "mon", "tue", "wed", "thu"))
        self.assertEqual((s.hours.start, s.hours.end), (time(8, 0), time(17, 0)))
        self.assertEqual(s.number_system, "western")
        self.assertEqual(s.timezone, "Asia/Riyadh")
        self.assertEqual(s.applied_overrides, ())
        self.assertEqual(s.evidence_status, "unverified")  # carried through, never hidden

    def test_ae_defaults_differ_from_sa(self) -> None:
        s = resolve("AE")
        self.assertEqual(s.week_start, "mon")
        self.assertEqual(s.weekend_days, ("sat", "sun"))

    def test_every_shipped_pack_resolves(self) -> None:
        for cc in ("SA", "AE", "EG", "QA"):
            with self.subTest(cc=cc):
                s = resolve(cc)
                self.assertFalse(set(s.weekend_days) & set(s.work_days))

    def test_eg_has_no_reduced_period_by_default(self) -> None:
        self.assertEqual(resolve("EG").reduced_periods, ())

    def test_settings_are_immutable(self) -> None:
        with self.assertRaises(Exception):
            resolve("SA").week_start = "mon"  # type: ignore[misc]

    def test_nested_labels_are_immutable(self) -> None:
        period = resolve("SA").reduced_periods[0]
        self.assertIsInstance(period.labels, tuple)  # sorted (language, text) pairs
        self.assertEqual([k for k, _ in period.labels], sorted(k for k, _ in period.labels))
        with self.assertRaises(TypeError):
            period.labels[0] = ("en", "changed")  # type: ignore[index]
        self.assertNotIn("changed", [v for _, v in resolve("SA").reduced_periods[0].labels])

    def test_label_lookup(self) -> None:
        period = resolve("SA").reduced_periods[0]
        self.assertEqual(period.label("en"), dict(period.labels)["en"])
        self.assertIsNone(period.label("fr"))


class TestSettingsAreValues(unittest.TestCase):
    """L2: a settings object with a reduced period must hash, copy, pickle and convert to plain data."""

    def test_hash_and_equality(self) -> None:
        a, b = resolve("SA"), resolve("SA")
        self.assertTrue(a.reduced_periods)
        self.assertEqual(hash(a), hash(b))
        self.assertEqual(a, b)
        self.assertEqual(len({a, b, resolve("AE")}), 2)
        self.assertNotEqual(a, resolve("SA", {"week": {"startDay": "sat"}}))

    def test_deepcopy(self) -> None:
        s = resolve("SA")
        c = copy.deepcopy(s)
        self.assertEqual(c, s)
        self.assertIsNot(c, s)
        self.assertEqual(copy.copy(s), s)

    def test_pickle_round_trip(self) -> None:
        s = resolve("SA", {"numberSystem": "eastern_arabic"})
        for proto in range(pickle.HIGHEST_PROTOCOL + 1):
            with self.subTest(protocol=proto):
                self.assertEqual(pickle.loads(pickle.dumps(s, protocol=proto)), s)

    def test_asdict(self) -> None:
        s = resolve("SA")
        d = dataclasses.asdict(s)
        self.assertEqual(d["country_code"], "SA")
        period = d["reduced_periods"][0]
        self.assertEqual(period["id"], "ramadan_hours")
        self.assertEqual(dict(period["labels"])["en"], s.reduced_periods[0].label("en"))
        self.assertEqual(period["hours"]["start"], time(9, 0))


class TestCompanyOverrides(unittest.TestCase):
    def test_overrides_replace_pack_values(self) -> None:
        s = resolve("SA", {
            "week": {"startDay": "sat", "weekendDays": ["fri"]},
            "workingTime": {"workDays": ["sat", "sun", "mon", "tue", "wed", "thu"],
                            "hours": {"from": "07:30", "to": "15:30"}},
            "numberSystem": "eastern_arabic",
        })
        self.assertEqual(s.week_start, "sat")
        self.assertEqual(s.weekend_days, ("fri",))
        self.assertEqual(len(s.work_days), 6)
        self.assertEqual(s.hours.start, time(7, 30))
        self.assertEqual(s.number_system, "eastern_arabic")
        self.assertIn("week.startDay", s.applied_overrides)

    def test_locked_and_unknown_paths_rejected(self) -> None:
        for bad in ({"currency": "USD"}, {"holidays": {"calendarRef": {"id": "sa.holidays", "version": "0.1.0"}}},
                    {"week": {"firstDay": "sat"}}):
            with self.subTest(bad=bad), self.assertRaises(OverrideRejectedError):
                resolve("SA", bad)

    def test_invalid_values_rejected(self) -> None:
        cases = [
            {"week": {"startDay": "funday"}},
            {"week": {"weekendDays": ["fri", "fri"]}},
            {"week": {"weekendDays": ["sun"]}},  # overlaps work days
            {"workingTime": {"hours": {"from": "17:00", "to": "08:00"}}},
            {"workingTime": {"hours": {"from": "8:00", "to": "17:00"}}},
            {"workingTime": {"workDays": []}},
            {"numberSystem": "latn"},
            {"numberSystem": "arab"},
        ]
        for bad in cases:
            with self.subTest(bad=bad), self.assertRaises(OverrideRejectedError):
                resolve("SA", bad)

    def test_unknown_country_fails_closed(self) -> None:
        with self.assertRaises(UnknownCountryError):
            resolve("XX")

    def test_week_start_must_be_known_weekday_only_not_forced_to_be_a_work_day(self) -> None:
        # Starting the week on a weekend day is a valid Saudi/Egyptian-style choice.
        self.assertEqual(resolve("SA", {"week": {"startDay": "sat"}}).week_start, "sat")

    def test_overrides_do_not_mutate_input(self) -> None:
        ov = {"week": {"startDay": "sat"}}
        resolve("SA", ov)
        self.assertEqual(ov, {"week": {"startDay": "sat"}})

    def test_day_in_neither_list_is_not_a_work_day_and_not_a_weekend(self) -> None:
        # A day that is neither work day nor weekend is allowed (half days, rotas); it is not a work day.
        s = resolve("SA", {"workingTime": {"workDays": ["sun", "mon", "tue", "wed"]}})
        self.assertFalse(s.is_work_day(date(2026, 11, 26)))  # Thursday
        self.assertFalse(s.is_weekend(date(2026, 11, 26)))
        self.assertIsNone(s.hours_on(date(2026, 11, 26)))  # no hours on a day that is not a work day

    def test_production_is_the_default_and_refuses_uncertified_packs(self) -> None:
        # No environment argument: production, which refuses every shipped (uncertified) pack.
        for code in ("SA", "AE", "EG", "QA"):
            with self.subTest(code=code), self.assertRaises(PackValidationError):
                resolve_calendar_settings(code, PACKS_DIR, version="0.1.0")
        with self.assertRaises(PackValidationError):
            resolve_calendar_settings("SA", PACKS_DIR, version="0.1.0", environment="production")

    def test_unknown_environment_refused(self) -> None:
        with self.assertRaises(CountryPackError):
            resolve_calendar_settings("SA", PACKS_DIR, version="0.1.0", environment="prod")


class TestDayClassification(unittest.TestCase):
    def test_weekend_and_work_day(self) -> None:
        s = resolve("SA")
        self.assertTrue(s.is_weekend(date(2026, 11, 27)))   # Friday
        self.assertTrue(s.is_weekend(date(2026, 11, 28)))   # Saturday
        self.assertTrue(s.is_work_day(date(2026, 11, 29)))  # Sunday
        self.assertFalse(s.is_work_day(date(2026, 11, 27)))
        ae = resolve("AE")
        self.assertTrue(ae.is_work_day(date(2026, 11, 27)))
        self.assertTrue(ae.is_weekend(date(2026, 11, 29)))

    def test_timestamps_and_strings_refused(self) -> None:
        s = resolve("SA")
        for bad in (datetime(2026, 11, 29, 10, 0), "2026-11-29", None):
            with self.subTest(bad=bad), self.assertRaises(CalendarSettingsError):
                s.is_work_day(bad)  # type: ignore[arg-type]

    def test_week_start_date(self) -> None:
        # Wednesday 2026-11-25
        d = date(2026, 11, 25)
        self.assertEqual(resolve("SA").week_start_date(d), date(2026, 11, 22))   # Sunday
        self.assertEqual(resolve("AE").week_start_date(d), date(2026, 11, 23))   # Monday
        self.assertEqual(resolve("SA", {"week": {"startDay": "sat"}}).week_start_date(d), date(2026, 11, 21))
        self.assertEqual(resolve("SA").week_start_date(date(2026, 11, 22)), date(2026, 11, 22))

    def test_week_start_date_before_the_calendar_range_fails_closed(self) -> None:
        with self.assertRaises(CalendarSettingsError) as ctx:
            resolve("SA").week_start_date(date.min)
        self.assertEqual(ctx.exception.code, "calendar_range")


class TestRamadanHours(unittest.TestCase):
    # Ramadan 1447 AH per the pinned Umm al-Qura tables (hijridate 2.6.0): 2026-02-18 to 2026-03-19 (30 days).
    def test_ramadan_range_comes_from_the_library(self) -> None:
        s = resolve("SA")
        r = s.ramadan_range(1447)
        self.assertEqual((r.start, r.end, r.source), (date(2026, 2, 18), date(2026, 3, 19), "computed"))
        self.assertEqual(s.ramadan_range(1448).start, date(2027, 2, 8))

    def test_ramadan_range_out_of_table_fails_closed(self) -> None:
        s = resolve("SA")
        for year in (1300, 1600, 0, -5):
            with self.subTest(year=year), self.assertRaises(CalendarSettingsError):
                s.ramadan_range(year)
        for bad in ("1447", 1447.0, True, None):
            with self.subTest(bad=bad), self.assertRaises(CalendarSettingsError):
                s.ramadan_range(bad)  # type: ignore[arg-type]

    def test_hours_during_ramadan_use_the_reduced_period(self) -> None:
        s = resolve("SA")
        h = s.hours_on(date(2026, 2, 22))  # Sunday inside Ramadan
        self.assertEqual((h.start, h.end, h.period_id), (time(9, 0), time(15, 0), "ramadan_hours"))
        self.assertEqual(h.source, "computed")

    def test_boundaries(self) -> None:
        s = resolve("SA")
        self.assertIsNone(s.hours_on(date(2026, 2, 17)).period_id)   # Tuesday, day before 1 Ramadan
        self.assertEqual(s.hours_on(date(2026, 2, 18)).period_id, "ramadan_hours")  # Wednesday, 1 Ramadan
        self.assertEqual(s.hours_on(date(2026, 3, 19)).period_id, "ramadan_hours")  # last day, Thursday
        self.assertIsNone(s.hours_on(date(2026, 3, 22)).period_id)  # first work day after Ramadan

    def test_normal_hours_outside_ramadan(self) -> None:
        h = resolve("SA").hours_on(date(2026, 6, 1))
        self.assertEqual((h.start, h.end, h.period_id, h.source), (time(8, 0), time(17, 0), None, "regular"))

    def test_weekend_has_no_hours_even_in_ramadan(self) -> None:
        self.assertIsNone(resolve("SA").hours_on(date(2026, 2, 20)))  # Friday in Ramadan

    def test_each_pack_ramadan_hours(self) -> None:
        d = date(2026, 3, 2)  # Monday in Ramadan 1447
        self.assertEqual(resolve("AE").hours_on(d).end, time(15, 0))
        self.assertEqual(resolve("QA").hours_on(d).end, time(14, 0))
        self.assertIsNone(resolve("EG").hours_on(d).period_id)

    def test_company_can_set_own_ramadan_hours_and_remove_them(self) -> None:
        red = [{"id": "ramadan", "labels": {"ar": "رمضان", "en": "Ramadan"}, "rule": "ramadan",
                "hours": {"from": "09:00", "to": "14:00"}}]
        s = resolve("SA", {"workingTime": {"reducedPeriods": red}})
        self.assertEqual(s.hours_on(date(2026, 2, 22)).end, time(14, 0))
        none = resolve("SA", {"workingTime": {"reducedPeriods": []}})
        self.assertIsNone(none.hours_on(date(2026, 2, 22)).period_id)

    def test_fixed_dates_period(self) -> None:
        red = [{"id": "summer", "labels": {"ar": "صيف", "en": "Summer"}, "rule": "fixed_dates",
                "gregorianFrom": "2026-07-01", "gregorianTo": "2026-08-31", "hours": {"from": "07:00", "to": "13:00"}}]
        s = resolve("EG", {"workingTime": {"reducedPeriods": red}})
        self.assertEqual(s.hours_on(date(2026, 7, 1)).period_id, "summer")
        self.assertEqual(s.hours_on(date(2026, 8, 31)).source, "fixed_dates")
        self.assertIsNone(s.hours_on(date(2026, 9, 1)).period_id)

    def test_overlapping_ramadan_and_fixed_period_is_ambiguous_and_fails_closed(self) -> None:
        red = [
            {"id": "ramadan", "labels": {"ar": "رمضان", "en": "Ramadan"}, "rule": "ramadan",
             "hours": {"from": "09:00", "to": "14:00"}},
            {"id": "winter", "labels": {"ar": "شتاء", "en": "Winter"}, "rule": "fixed_dates",
             "gregorianFrom": "2026-02-01", "gregorianTo": "2026-02-28", "hours": {"from": "08:00", "to": "15:00"}},
        ]
        s = resolve("SA", {"workingTime": {"reducedPeriods": red}})
        with self.assertRaises(CalendarSettingsError):
            s.hours_on(date(2026, 2, 22))
        self.assertEqual(s.hours_on(date(2026, 2, 10)).period_id, "winter")

    def test_date_outside_hijri_table_fails_closed_when_ramadan_rule_exists(self) -> None:
        sa = resolve("SA")
        for day in (date(1924, 7, 31), date(2077, 11, 17), date(1900, 1, 3)):  # all work days (Sun to Thu)
            with self.subTest(day=day), self.assertRaises(CalendarSettingsError) as ctx:
                sa.hours_on(day)
            self.assertEqual(ctx.exception.code, "calendar_range")

    def test_table_edges_still_resolve(self) -> None:
        sa = resolve("SA")
        self.assertEqual(sa.hours_on(date(2077, 11, 16)).source, "regular")  # last day of 1500 AH, a Sunday
        self.assertIsNone(sa.hours_on(date(1924, 8, 1)))  # first table day (a Friday)

    def test_out_of_table_dates_do_not_fail_when_the_tables_are_not_used(self) -> None:
        # No ramadan rule (EG), or a weekend day: hours_on never reaches the Umm al-Qura tables.
        self.assertEqual(resolve("EG").hours_on(date(1900, 1, 2)).source, "regular")
        self.assertIsNone(resolve("SA").hours_on(date(1900, 1, 5)))  # Friday
        fixed = [{"id": "old", "labels": {"ar": "قديم", "en": "Old"}, "rule": "fixed_dates",
                  "gregorianFrom": "1900-01-01", "gregorianTo": "1900-12-31", "hours": {"from": "07:00", "to": "13:00"}}]
        self.assertEqual(resolve("EG", {"workingTime": {"reducedPeriods": fixed}}).hours_on(date(1900, 1, 2)).period_id, "old")
        # Day classification and week start use no tables either.
        self.assertTrue(resolve("SA").is_work_day(date(1900, 1, 3)))
        self.assertEqual(resolve("SA").week_start_date(date(1900, 1, 3)), date(1899, 12, 31))  # Wednesday to the Sunday before

    def test_ramadan_period_with_gregorian_dates_is_refused(self) -> None:
        # The pack framework accepts these keys on any rule; for `ramadan` they would be silently ignored.
        for extra in ({"gregorianFrom": "2026-01-01"}, {"gregorianTo": "2026-12-31"},
                      {"gregorianFrom": "2026-01-01", "gregorianTo": "2026-12-31"}):
            with self.subTest(extra=extra):
                red = [{"id": "ramadan", "labels": {"ar": "رمضان", "en": "Ramadan"}, "rule": "ramadan",
                        "hours": {"from": "09:00", "to": "14:00"}, **extra}]
                with self.assertRaises(CalendarSettingsError) as ctx:
                    resolve("SA", {"workingTime": {"reducedPeriods": red}})
                self.assertEqual(ctx.exception.code, "invalid_reduced_period")


class TestNumberSystem(unittest.TestCase):
    def test_western_leaves_digits(self) -> None:
        self.assertEqual(resolve("SA").format_digits("08:00 12/03"), "08:00 12/03")

    def test_eastern_arabic_translates_ascii_digits_only(self) -> None:
        s = resolve("SA", {"numberSystem": "eastern_arabic"})
        self.assertEqual(s.format_digits("08:00 abc"), "٠٨:٠٠ abc")
        self.assertEqual(s.format_digits("٠٨"), "٠٨")

    def test_non_string_refused(self) -> None:
        with self.assertRaises(CalendarSettingsError):
            resolve("SA").format_digits(8)  # type: ignore[arg-type]


class TestSource(unittest.TestCase):
    SETTINGS = Path(__file__).resolve().parents[1] / "settings.py"
    # Numbers the module may contain: 0 and 1 (offsets, counts), 7 (days a week), 9 (Ramadan is Hijri month 9).
    ALLOWED_NUMBERS = {0, 1, 7, 9}

    def test_no_statutory_limit_or_lunar_arithmetic_constants_in_code(self) -> None:
        # Hour caps (48), lunar-year lengths (354, 355), the synodic month (29.53), month lengths (29, 30) or any
        # other literal number would show up here: only the allowed numbers may appear as code constants.
        tree = ast.parse(self.SETTINGS.read_text(encoding="utf-8"))
        numbers = {n.value for n in ast.walk(tree)
                   if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool)}
        self.assertLessEqual(numbers, self.ALLOWED_NUMBERS)

    def test_source_check_detects_a_planted_constant(self) -> None:
        planted = ast.parse("MAX_WEEKLY_HOURS = 48")
        numbers = {n.value for n in ast.walk(planted) if isinstance(n, ast.Constant)}
        self.assertFalse(numbers <= self.ALLOWED_NUMBERS)


class TestHijridatePin(unittest.TestCase):
    """L4: one runtime pin (the engine package) and a CI pin that must match it."""

    PIN = re.compile(r"hijridate==([0-9][0-9A-Za-z.]*)")

    def test_ci_step_pin_equals_runtime_pin(self) -> None:
        runtime = self.PIN.findall((REPO_ROOT / "apps/engine/change_engine/pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(len(runtime), 1)
        workflow = (REPO_ROOT / ".github/workflows/tests.yml").read_text(encoding="utf-8")
        step = re.search(r"- name: Company calendar settings tests \(CMP-023\)\n(.*?)(?=\n      - name:|\Z)", workflow, re.S)
        self.assertIsNotNone(step)
        self.assertEqual(self.PIN.findall(step.group(1)), runtime)

    def test_installed_library_is_the_pinned_version(self) -> None:
        runtime = self.PIN.findall((REPO_ROOT / "apps/engine/change_engine/pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual([metadata.version("hijridate")], runtime)


if __name__ == "__main__":
    unittest.main()
