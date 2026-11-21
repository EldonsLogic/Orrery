"""Contract tests for the engine's Umm al-Qura date boundary."""

import unittest
from datetime import date

from change_engine.calendar_dates import gregorian_to_hijri, hijri_to_gregorian


class CalendarDatesTest(unittest.TestCase):
    def test_conversion_matches_existing_intake_example(self):
        self.assertEqual(hijri_to_gregorian(1446, 3, 15), date(2024, 9, 18))
        self.assertEqual(gregorian_to_hijri(date(2024, 9, 18)), "1446-03-15")

    def test_invalid_and_out_of_range_dates_are_rejected(self):
        for parts in ((1446, 13, 1), (1300, 1, 1), (1501, 1, 1)):
            with self.subTest(parts=parts), self.assertRaises(ValueError):
                hijri_to_gregorian(*parts)
        with self.assertRaises(ValueError):
            gregorian_to_hijri(date(1800, 1, 1))

    def test_datetime_is_not_accepted_as_a_date(self):
        from datetime import datetime

        with self.assertRaises(TypeError):
            gregorian_to_hijri(datetime(2024, 9, 18, 23, 0))
