"""SIM-xxx anomaly codes, severities and the anomaly record. Messages are i18n keys, never free text.

Severity: `blocking` means the record or metric did not go through (excluded, not run, mismatched or the run
aborted); `warning` needs the owner's or accountant's look; `info` is evidence only.
"""
from __future__ import annotations

from dataclasses import dataclass, field

CODES = {
    # Source data (found before any call).
    "SIM-101": ("unmapped_account", "warning"),
    "SIM-102": ("rounding_difference", "info"),
    "SIM-103": ("missing_tax_code", "warning"),
    "SIM-104": ("negative_stock", "warning"),
    "SIM-105": ("duplicate_document", "blocking"),
    "SIM-106": ("possible_duplicate", "warning"),
    "SIM-107": ("date_outside_month", "blocking"),
    "SIM-112": ("intake_quality_flag", "info"),
    "SIM-113": ("unallocated_payment", "warning"),
    "SIM-114": ("invalid_source_value", "blocking"),
    "SIM-115": ("inconsistent_document", "blocking"),
    "SIM-116": ("unknown_record_kind", "blocking"),
    # Planning (tool set and roles).
    "SIM-108": ("unmapped_record", "blocking"),
    "SIM-109": ("needs_approval", "info"),
    "SIM-110": ("caller_lacks_role", "blocking"),
    "SIM-111": ("invalid_arguments", "blocking"),
    "SIM-117": ("step_blocked", "blocking"),
    # Replay and comparison.
    "SIM-118": ("parked_by_approval_rule", "warning"),
    "SIM-120": ("port_error", "blocking"),
    "SIM-121": ("total_mismatch", "blocking"),
    "SIM-122": ("metric_not_compared", "warning"),
    "SIM-123": ("invalid_reported_amount", "blocking"),
}
SEVERITIES = ("blocking", "warning", "info")


@dataclass(frozen=True)
class Anomaly:
    code: str
    source_ids: tuple = ()
    params: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.code not in CODES:
            raise ValueError("unknown anomaly code")

    @property
    def severity(self) -> str:
        return CODES[self.code][1]

    def to_dict(self) -> dict:
        name, sev = CODES[self.code]
        return {"code": self.code, "severity": sev, "messageKey": f"sim.{name}",
                "sourceIds": sorted(self.source_ids), "params": dict(sorted(self.params.items()))}


def sort_anomalies(items) -> list:
    """Stable, deterministic order: severity, code, first source id, params."""
    rank = {s: i for i, s in enumerate(SEVERITIES)}
    return sorted(items, key=lambda a: (rank[a.severity], a.code, sorted(a.source_ids), sorted(map(str, a.params.items()))))
