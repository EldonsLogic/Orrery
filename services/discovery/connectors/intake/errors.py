"""Coded refusals of the document intake connector. The runner reports an extract fault as CON-010
plus the exception class name, so each code has its own class whose name carries the code."""


class IntakeRefusal(Exception):
    code = "INT-000"

    def __init__(self, reason: str = ""):
        super().__init__(f"{self.code}: {reason}" if reason else self.code)
        self.reason = reason


class Int001UnsupportedType(IntakeRefusal):
    """Not PDF, PNG, JPEG or TIFF by magic bytes. Extension and declared type are never consulted."""
    code = "INT-001"


class Int002Oversize(IntakeRefusal):
    code = "INT-002"


class Int003TooManyPages(IntakeRefusal):
    code = "INT-003"


class Int004ImageTooLarge(IntakeRefusal):
    """Header dimensions over the cap (decompression-bomb defence; headers only, no pixel decode)."""
    code = "INT-004"


class Int005Malformed(IntakeRefusal):
    code = "INT-005"


class Int006ActiveContent(IntakeRefusal):
    """PDF with JavaScript, launch, embedded-file, open or additional action, forms submit, rich media."""
    code = "INT-006"


class Int007Encrypted(IntakeRefusal):
    code = "INT-007"


class Int008OcrInvalid(IntakeRefusal):
    """The injected OCR engine returned something that is not a well-formed OcrResult."""
    code = "INT-008"


class Int009OcrFailed(IntakeRefusal):
    code = "INT-009"
