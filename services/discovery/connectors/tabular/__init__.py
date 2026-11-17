"""Excel (.xlsx) and CSV import connector (DSC-011), tier 2 file upload. See services/discovery/README.md."""
from .connector import TabularConnector, register
from .errors import (Tab001UnsupportedFormat, Tab002Encrypted, Tab003UnsafeArchive, Tab004DtdRefused,
                     Tab005MacroRefused, Tab006Malformed, Tab007Undecodable, TabularRefusal)

__all__ = ["TabularConnector", "register", "TabularRefusal", "Tab001UnsupportedFormat", "Tab002Encrypted",
           "Tab003UnsafeArchive", "Tab004DtdRefused", "Tab005MacroRefused", "Tab006Malformed",
           "Tab007Undecodable"]
