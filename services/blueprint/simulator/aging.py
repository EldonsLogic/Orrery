"""Aging buckets, shared by the expected totals and the simulated port (one tested function).

age = days from the due date (or the posting date when there is none) to the period end.
age <= 0 is `not_due` (due today is not overdue); 1 to 30 days overdue is `0_30`, then 31_60, 61_90, over_90.
"""
BUCKETS = ("not_due", "0_30", "31_60", "61_90", "over_90")


def aging_bucket(age_days: int) -> str:
    if age_days <= 0:
        return "not_due"
    for limit, name in ((30, "0_30"), (60, "31_60"), (90, "61_90")):
        if age_days <= limit:
            return name
    return "over_90"
