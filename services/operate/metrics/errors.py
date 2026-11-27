"""Refusal codes. Messages carry no data values; customer text comes from the i18n catalog by `code`."""

CODES = {
    "MET-001": "unknown_metric",
    "MET-002": "permission_denied",
    "MET-003": "invalid_params",
    "MET-004": "tenant_mismatch",
    "MET-005": "currency_mismatch",
    "MET-006": "bad_event_data",
    "MET-007": "no_principal",
}


class MetricError(Exception):
    def __init__(self, code: str):
        self.code = code
        self.reason = CODES[code]
        super().__init__(f"{code} {self.reason}")
