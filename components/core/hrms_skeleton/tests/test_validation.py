"""Exact decimal, date, text and record validation (ERP-010, ADR-0031)."""

from __future__ import annotations

import datetime as dt
import unittest
from decimal import Decimal

from components.core.hrms_skeleton import HrmsError
from components.core.hrms_skeleton.specs import DAYS, MONEY, RATIO, SPECS
from components.core.hrms_skeleton.validation import (
    normalise_record,
    normalise_value,
    parse_date,
    parse_decimal,
)

CO = "Acme Trading"


def code(fn, *args, **kwargs):
    with unittest.TestCase().assertRaises(HrmsError) as ctx:
        fn(*args, **kwargs)
    return ctx.exception.code


class DecimalTests(unittest.TestCase):
    def test_exact_values_accepted_without_float_error(self):
        self.assertEqual(parse_decimal("0.10", MONEY, "base"), Decimal("0.10"))
        self.assertEqual(parse_decimal("12000.50", MONEY, "base"), Decimal("12000.50"))
        self.assertEqual(parse_decimal(5, DAYS, "d"), Decimal(5))
        self.assertEqual(parse_decimal(Decimal("21.5"), DAYS, "d"), Decimal("21.5"))
        self.assertEqual(normalise_value("10.500", DAYS, "d"), "10.5")
        self.assertEqual(normalise_value("0", MONEY, "m"), "0")
        self.assertEqual(normalise_value("100", MONEY, "m"), "100")

    def test_floats_and_bools_are_refused(self):
        for bad in (0.1, 1.0, float("nan"), float("inf"), True, False):
            self.assertEqual(code(parse_decimal, bad, MONEY, "base"), "invalid_decimal")

    def test_nan_infinity_and_odd_strings_are_refused(self):
        for bad in (Decimal("NaN"), Decimal("sNaN"), Decimal("Infinity"), Decimal("-Infinity"),
                    "NaN", "Infinity", "-Infinity", "1e3", "1E3", "1_000", " 5", "5 ", "", ".5", "5.",
                    "+5", "05", "1,000", "٣", "١٢", "0x10", None, [], "5\n", object()):
            self.assertEqual(code(parse_decimal, bad, MONEY, "base"), "invalid_decimal", repr(bad))

    def test_negative_values_are_out_of_range(self):
        for bad in ("-1", "-0.01", -1, Decimal("-5")):
            self.assertIn(code(parse_decimal, bad, MONEY, "base"), ("invalid_decimal", "decimal_out_of_range"))
        self.assertEqual(code(parse_decimal, Decimal("-0.01"), MONEY, "base"), "decimal_out_of_range")
        self.assertEqual(code(parse_decimal, -1, DAYS, "d"), "decimal_out_of_range")

    def test_upper_bounds_and_precision(self):
        self.assertEqual(code(parse_decimal, "3661", DAYS, "d"), "decimal_out_of_range")
        self.assertEqual(code(parse_decimal, "1000000000000", MONEY, "m"), "decimal_out_of_range")
        self.assertEqual(code(parse_decimal, "0.001", MONEY, "m"), "decimal_precision_exceeded")
        self.assertEqual(code(parse_decimal, "0.12345", RATIO, "r"), "decimal_precision_exceeded")
        self.assertEqual(parse_decimal("0.1234", RATIO, "r"), Decimal("0.1234"))
        self.assertEqual(code(parse_decimal, "1.0001", RATIO, "r"), "decimal_out_of_range")
        self.assertEqual(parse_decimal("1", RATIO, "r"), Decimal(1))


class DateTests(unittest.TestCase):
    def test_valid_dates(self):
        self.assertEqual(parse_date("2026-02-28", "d"), "2026-02-28")
        self.assertEqual(parse_date(dt.date(2028, 2, 29), "d"), "2028-02-29")

    def test_invalid_dates(self):
        for bad in ("2026-02-30", "2026-13-01", "2026-1-1", "26-01-01", "2026/01/01", "2026-01-01T00:00:00",
                    "1800-01-01", "2200-01-01", "", " 2026-01-01", "٢٠٢٦-٠١-٠١", None, 20260101,
                    dt.datetime(2026, 1, 1), dt.datetime(2026, 1, 1, 12, 0)):
            self.assertEqual(code(parse_date, bad, "d"), "invalid_date", repr(bad))

    def test_range_checked_for_leave_records(self):
        base = {"employee": "EMP-1", "leave_type": "Annual", "from_date": "2026-03-10", "to_date": "2026-03-09"}
        self.assertEqual(code(normalise_record, SPECS["Leave Application"], base, CO), "date_range_invalid")
        same_day = {**base, "to_date": "2026-03-10"}
        self.assertEqual(normalise_record(SPECS["Leave Application"], same_day, CO)["to_date"], "2026-03-10")
        period = {"from_date": "2026-12-31", "to_date": "2026-01-01"}
        self.assertEqual(code(normalise_record, SPECS["Leave Period"], period, CO), "date_range_invalid")


class TextAndChoiceTests(unittest.TestCase):
    def test_text_is_stripped_and_controls_refused(self):
        self.assertEqual(normalise_value("  Sales  ", SPECS["Branch"].fields["branch"], "branch"), "Sales")
        rule = SPECS["Branch"].fields["branch"]
        for bad in ("", "   ", "a\x00b", "a\nb", "a​b", "x" * 141, 5, None, ["a"]):
            self.assertEqual(code(normalise_value, bad, rule, "branch"), "invalid_text", repr(bad))
        desc = SPECS["Designation"].fields["description"]
        self.assertEqual(normalise_value("line one\nline two", desc, "description"), "line one\nline two")

    def test_enum_and_bool(self):
        status = SPECS["Employee"].fields["status"]
        self.assertEqual(normalise_value("Active", status, "status"), "Active")
        for bad in ("active", "Retired", "", None, 1):
            self.assertEqual(code(normalise_value, bad, status, "status"), "invalid_choice")
        flag = SPECS["Department"].fields["is_group"]
        self.assertIs(normalise_value(True, flag, "is_group"), True)
        for bad in (1, 0, "true", "yes", None):
            self.assertEqual(code(normalise_value, bad, flag, "is_group"), "invalid_boolean")


class RecordTests(unittest.TestCase):
    def test_employee_company_is_filled_in(self):
        rec = normalise_record(SPECS["Employee"], {"employee_number": "E1", "first_name": "Lina",
                                                    "date_of_joining": "2026-01-05"}, CO)
        self.assertEqual(rec["company"], CO)

    def test_company_mismatch_and_unknown_company_field(self):
        spec = SPECS["Employee"]
        base = {"employee_number": "E1", "first_name": "Lina", "date_of_joining": "2026-01-05"}
        self.assertEqual(code(normalise_record, spec, {**base, "company": "Other Co"}, CO), "company_mismatch")
        self.assertEqual(normalise_record(spec, {**base, "company": CO}, CO)["company"], CO)
        # A doctype with no company field refuses one outright.
        self.assertEqual(code(normalise_record, SPECS["Branch"], {"branch": "HQ", "company": CO}, CO),
                         "field_not_allowed")

    def test_required_fields(self):
        self.assertEqual(code(normalise_record, SPECS["Employee"], {"first_name": "Lina"}, CO), "field_required")
        self.assertEqual(code(normalise_record, SPECS["Salary Structure Assignment"],
                              {"employee": "E", "salary_structure": "S", "from_date": "2026-01-01"}, CO),
                         "field_required")

    def test_unknown_fields_are_refused(self):
        self.assertEqual(code(normalise_record, SPECS["Branch"], {"branch": "HQ", "docstatus": 1}, CO),
                         "field_not_allowed")
        self.assertEqual(code(normalise_record, SPECS["Leave Application"],
                              {"employee": "E", "leave_type": "A", "from_date": "2026-01-01",
                               "to_date": "2026-01-02", "status": "Approved"}, CO), "field_not_allowed")

    def test_caller_supplied_identity_is_refused(self):
        for name in ("roles", "user_roles", "caller_roles", "user", "approver", "tenant", "site", "owner"):
            self.assertEqual(code(normalise_record, SPECS["Branch"], {"branch": "HQ", name: "x"}, CO),
                             "caller_identity_not_accepted", name)

    def test_payroll_logic_is_refused(self):
        spec = SPECS["Salary Component"]
        base = {"salary_component": "Basic", "type": "Earning"}
        for name in ("formula", "condition", "amount_based_on_formula", "depends_on_payment_days",
                     "is_tax_applicable", "gosi_rate", "end_of_service", "gratuity", "tax_rate"):
            self.assertEqual(code(normalise_record, spec, {**base, name: "base * 0.1"}, CO),
                             "payroll_logic_not_allowed", name)

    def test_salary_structure_children(self):
        spec = SPECS["Salary Structure"]
        ok = {"name": "Standard", "earnings": [{"salary_component": "Basic", "amount": "9000.00"},
                                               {"salary_component": "Housing", "amount": 2500}],
              "deductions": []}
        rec = normalise_record(spec, ok, CO)
        self.assertEqual(rec["earnings"], [{"salary_component": "Basic", "amount": "9000"},
                                           {"salary_component": "Housing", "amount": "2500"}])
        bad_cases = {
            "invalid_list": {**ok, "earnings": "Basic"},
            "payroll_logic_not_allowed": {**ok, "earnings": [{"salary_component": "B", "amount": "1", "formula": "base"}]},
            "field_required": {**ok, "earnings": [{"salary_component": "B"}]},
            "duplicate_row": {**ok, "earnings": [{"salary_component": "B", "amount": "1"},
                                                 {"salary_component": "B", "amount": "2"}]},
            "invalid_decimal": {**ok, "earnings": [{"salary_component": "B", "amount": 1.5}]},
            "field_not_allowed": {**ok, "earnings": [{"salary_component": "B", "amount": "1", "idx": 3}]},
        }
        for expected, payload in bad_cases.items():
            self.assertEqual(code(normalise_record, spec, payload, CO), expected)
        self.assertEqual(code(normalise_record, spec, {**ok, "earnings": [5]}, CO), "invalid_list")

    def test_non_mapping_payload(self):
        for bad in (None, [], "Branch", 5):
            self.assertEqual(code(normalise_record, SPECS["Branch"], bad, CO), "payload_invalid")


if __name__ == "__main__":
    unittest.main()
