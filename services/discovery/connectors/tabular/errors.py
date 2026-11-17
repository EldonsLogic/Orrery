"""Coded refusals of the tabular connector. The runner reports an extract fault as CON-010 plus
the exception class name, so each code has its own class whose name carries the code."""


class TabularRefusal(Exception):
    code = "TAB-000"

    def __init__(self, reason: str = ""):
        super().__init__(f"{self.code}: {reason}" if reason else self.code)
        self.reason = reason


class Tab001UnsupportedFormat(TabularRefusal):
    """Legacy .xls (OLE), .xlsb, .ods, PDF or other binary: never guessed."""
    code = "TAB-001"


class Tab002Encrypted(TabularRefusal):
    code = "TAB-002"


class Tab003UnsafeArchive(TabularRefusal):
    """Zip bomb, too many entries, nested archive, zip64, path traversal, odd compression."""
    code = "TAB-003"


class Tab004DtdRefused(TabularRefusal):
    """DOCTYPE or ENTITY in an XML part."""
    code = "TAB-004"


class Tab005MacroRefused(TabularRefusal):
    code = "TAB-005"


class Tab006Malformed(TabularRefusal):
    code = "TAB-006"


class Tab007Undecodable(TabularRefusal):
    code = "TAB-007"
