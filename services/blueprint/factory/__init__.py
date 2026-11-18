"""Component factory sandbox (BPL-015). See services/blueprint/README.md."""
from .errors import FacError, Finding
from .runner import Report, check, write_report

__all__ = ["check", "write_report", "Report", "Finding", "FacError"]
