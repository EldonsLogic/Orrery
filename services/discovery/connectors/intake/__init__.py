"""Document intake with Arabic OCR (DSC-014), tier 3 document OCR. The OCR engine is injected; see
services/discovery/README.md and docs/security/prompt-injection-defence.md."""
from .connector import IntakeConnector, register
from .errors import (Int001UnsupportedType, Int002Oversize, Int003TooManyPages, Int004ImageTooLarge,
                     Int005Malformed, Int006ActiveContent, Int007Encrypted, Int008OcrInvalid, Int009OcrFailed,
                     IntakeRefusal)
from .ocr import OcrEngine, OcrResult, OcrToken

__all__ = ["IntakeConnector", "register", "OcrEngine", "OcrResult", "OcrToken", "IntakeRefusal",
           "Int001UnsupportedType", "Int002Oversize", "Int003TooManyPages", "Int004ImageTooLarge",
           "Int005Malformed", "Int006ActiveContent", "Int007Encrypted", "Int008OcrInvalid", "Int009OcrFailed"]
