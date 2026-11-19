"""Declarative table of the twelve in-scope doctypes: fields, keys, roles and value rules.

Field names follow the engine's HR doctypes and are UNVERIFIED against the pinned bench
(docs/open-questions.md, Q-280). A field that is not listed here is refused, so a wrong or
missing name fails closed rather than writing something unreviewed.

No field here carries payroll maths: formulas, conditions and calculated totals are not
accepted (`FORBIDDEN_PAYROLL_LOGIC_FIELDS`, ADR-0031).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

# Roles (engine role names, resolved from the authenticated session only).
HR_ADMIN_ROLES = frozenset({"HR Manager", "System Manager"})
HR_SETUP_ROLES = HR_ADMIN_ROLES | {"HR User"}
LEAVE_APPLY_ROLES = HR_SETUP_ROLES | {"Employee"}
LEAVE_DECISION_ROLES = HR_ADMIN_ROLES | {"Leave Approver"}

# Payroll behaviour the engine can attach to a salary component or structure. Refused outright:
# this component stores structure only and never takes a formula or rule that computes a figure.
FORBIDDEN_PAYROLL_LOGIC_FIELDS = frozenset(
    {
        "formula", "condition", "amount_based_on_formula", "depends_on_payment_days",
        "variable_based_on_taxable_salary", "is_tax_applicable", "is_flexible_benefit",
        "round_to_the_nearest_integer", "statistical_component", "do_not_include_in_total",
        "gosi", "gosi_rate", "social_security", "end_of_service", "gratuity", "tax", "tax_rate",
    }
)

# Standard document columns that are not DocFields: `meta.get_field("name")` returns None for them
# (frappe v15 Meta), so they are checked at document level, not by field lookup.
STANDARD_COLUMNS = frozenset({"name"})

# Names a caller may never put in a payload: identity and scope come from the session.
CALLER_IDENTITY_FIELDS = frozenset(
    {
        "roles", "user_roles", "caller_roles", "user", "approver", "tenant", "site", "site_id", "owner",
        "applicant_user",
    }
)


@dataclass(frozen=True)
class Rule:
    """How one field value is validated. kind: str, text, date, bool, decimal, enum."""

    kind: str
    maximum: Decimal | int | None = None  # str/text: max length; decimal: max value
    minimum: Decimal | None = None
    scale: int = 0  # decimal: most decimal places allowed
    choices: tuple[str, ...] = ()


STR = Rule("str", maximum=140)
TEXT = Rule("text", maximum=1000)
DATE = Rule("date")
BOOL = Rule("bool")
MONEY = Rule("decimal", minimum=Decimal(0), maximum=Decimal("999999999999"), scale=2)
DAYS = Rule("decimal", minimum=Decimal(0), maximum=Decimal("3660"), scale=2)
RATIO = Rule("decimal", minimum=Decimal(0), maximum=Decimal(1), scale=4)


def enum(*choices: str) -> Rule:
    return Rule("enum", choices=choices)


@dataclass(frozen=True)
class ChildSpec:
    """A child table reached only through its parent (never a directly addressable doctype)."""

    doctype: str
    fields: dict[str, Rule]
    required: tuple[str, ...]
    unique_by: str


@dataclass(frozen=True)
class DocSpec:
    doctype: str
    key_fields: tuple[str, ...]  # stable business key; with the tenant (and company) it is unique
    fields: dict[str, Rule]
    required: tuple[str, ...]
    write_roles: frozenset[str]
    company_scoped: bool = False  # has a company field; the key then includes the company
    employee_field: str | None = None  # must reference an employee of the scoped company
    date_range: tuple[str, str] | None = None
    children: dict[str, ChildSpec] = field(default_factory=dict)


_SALARY_DETAIL = ChildSpec(
    "Salary Detail", {"salary_component": STR, "amount": MONEY}, ("salary_component", "amount"), "salary_component"
)

_LEAVE_RANGE = ("from_date", "to_date")

SPECS: dict[str, DocSpec] = {
    # Setup
    "Employee": DocSpec(
        "Employee", ("employee_number",),
        {
            "employee_number": STR, "first_name": STR, "last_name": STR, "company": STR,
            "gender": STR, "date_of_birth": DATE,
            "department": STR, "designation": STR, "branch": STR, "date_of_joining": DATE,
            "status": enum("Active", "Inactive", "Suspended", "Left"), "user_id": STR,
            "leave_approver": STR, "holiday_list": STR,
        },
        ("employee_number", "first_name", "gender", "date_of_birth", "date_of_joining"), HR_ADMIN_ROLES,
        company_scoped=True,
    ),
    "Department": DocSpec(
        "Department", ("department_name",),
        {"department_name": STR, "company": STR, "parent_department": STR, "is_group": BOOL},
        ("department_name",), HR_SETUP_ROLES, company_scoped=True,
    ),
    "Designation": DocSpec(
        "Designation", ("designation_name",), {"designation_name": STR, "description": TEXT},
        ("designation_name",), HR_SETUP_ROLES,
    ),
    "Branch": DocSpec("Branch", ("branch",), {"branch": STR}, ("branch",), HR_SETUP_ROLES),
    # HR
    "Leave Type": DocSpec(
        "Leave Type", ("leave_type_name",),
        {
            "leave_type_name": STR, "max_leaves_allowed": DAYS, "max_continuous_days_allowed": DAYS,
            "applicable_after": DAYS, "is_carry_forward": BOOL, "maximum_carry_forwarded_leaves": DAYS,
            "is_lwp": BOOL, "is_ppl": BOOL, "fraction_of_daily_salary_per_leave": RATIO,
            "include_holiday": BOOL, "allow_negative": BOOL,
        },
        ("leave_type_name",), HR_SETUP_ROLES,
    ),
    "Leave Period": DocSpec(
        "Leave Period", ("company", "from_date", "to_date"),
        {"company": STR, "from_date": DATE, "to_date": DATE, "is_active": BOOL},
        ("from_date", "to_date"), HR_SETUP_ROLES, company_scoped=True, date_range=_LEAVE_RANGE,
    ),
    "Leave Policy": DocSpec(
        "Leave Policy", ("title",), {"title": STR}, ("title",), HR_ADMIN_ROLES,
        children={
            "leave_policy_details": ChildSpec(
                "Leave Policy Detail", {"leave_type": STR, "annual_allocation": DAYS},
                ("leave_type", "annual_allocation"), "leave_type",
            )
        },
    ),
    "Leave Allocation": DocSpec(
        "Leave Allocation", ("employee", "leave_type", "from_date", "to_date"),
        {
            "employee": STR, "leave_type": STR, "from_date": DATE, "to_date": DATE,
            "new_leaves_allocated": DAYS, "company": STR,
        },
        ("employee", "leave_type", "from_date", "to_date", "new_leaves_allocated"), HR_ADMIN_ROLES,
        company_scoped=True, employee_field="employee", date_range=_LEAVE_RANGE,
    ),
    "Leave Application": DocSpec(
        "Leave Application", ("employee", "leave_type", "from_date", "to_date"),
        {
            "employee": STR, "leave_type": STR, "from_date": DATE, "to_date": DATE,
            "description": TEXT, "leave_approver": STR, "company": STR,
        },
        ("employee", "leave_type", "from_date", "to_date"), LEAVE_APPLY_ROLES,
        company_scoped=True, employee_field="employee", date_range=_LEAVE_RANGE,
    ),
    # Payroll structure only (CMP-015 builds the WPS/SIF output later)
    "Salary Component": DocSpec(
        "Salary Component", ("salary_component",),
        {
            "salary_component": STR, "salary_component_abbr": STR, "type": enum("Earning", "Deduction"),
            "description": TEXT, "amount": MONEY,
        },
        ("salary_component", "type"), HR_ADMIN_ROLES,
    ),
    "Salary Structure": DocSpec(
        "Salary Structure", ("name",),
        {
            "name": STR, "company": STR, "currency": STR, "is_active": enum("Yes", "No"),
            "payroll_frequency": enum("Monthly", "Fortnightly", "Bimonthly", "Weekly", "Daily"),
        },
        ("name",), HR_ADMIN_ROLES, company_scoped=True,
        children={"earnings": _SALARY_DETAIL, "deductions": _SALARY_DETAIL},
    ),
    "Salary Structure Assignment": DocSpec(
        "Salary Structure Assignment", ("employee", "salary_structure", "from_date"),
        {
            "employee": STR, "salary_structure": STR, "from_date": DATE, "company": STR,
            "currency": STR, "base": MONEY, "variable": MONEY,
        },
        ("employee", "salary_structure", "from_date", "base"), HR_ADMIN_ROLES,
        company_scoped=True, employee_field="employee",
    ),
}

# Order in which a whole configuration is applied: referenced records first.
APPLY_ORDER = (
    "Designation", "Branch", "Department", "Employee", "Leave Type", "Leave Period", "Leave Policy",
    "Leave Allocation", "Leave Application", "Salary Component", "Salary Structure",
    "Salary Structure Assignment",
)
assert set(APPLY_ORDER) == set(SPECS)
