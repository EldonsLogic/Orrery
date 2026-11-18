"""Attachment gate. Type is decided by content (magic bytes), never by extension or declared type.
Executables, scripts, shortcuts, macro-enabled Office files and archives are blocked. Allowed
attachments are routed to the existing connectors by the caller: discovery.intake (PDF, PNG, JPEG,
TIFF) and discovery.tabular (CSV, TSV, XLSX). Nothing is decoded or run here."""
from __future__ import annotations

import io
import re
import zipfile

from ..intake.gate import detect_type
from ..intake.errors import Int001UnsupportedType

EXEC_EXT = frozenset({
    "exe", "dll", "com", "scr", "pif", "cpl", "msi", "msp", "bat", "cmd", "ps1", "psm1", "vbs", "vbe", "js", "jse",
    "wsf", "wsh", "hta", "jar", "apk", "app", "sh", "bash", "command", "lnk", "url", "reg", "inf", "gadget", "scf",
    "py", "pyc", "rb", "pl", "php", "appx", "msix", "dmg", "pkg", "deb", "rpm", "bin", "elf", "so", "dylib",
    "docm", "xlsm", "pptm", "dotm", "xltm", "xlam", "ppam", "xlsb", "iso", "img", "vhd", "svg", "html", "htm"})
ARCHIVE_EXT = frozenset({"zip", "rar", "7z", "gz", "tgz", "tar", "bz2", "xz", "cab", "z"})
EXEC_MAGIC = ((b"MZ", "pe"), (b"\x7fELF", "elf"), (b"#!", "script"), (b"\xca\xfe\xba\xbe", "macho_or_class"),
              (b"\xfe\xed\xfa", "macho"), (b"\xcf\xfa\xed\xfe", "macho"), (b"\xce\xfa\xed\xfe", "macho"),
              (b"L\x00\x00\x00\x01\x14\x02", "lnk"), (b"\xd0\xcf\x11\xe0", "ole_compound"))
ARCHIVE_MAGIC = (b"Rar!", b"7z\xbc\xaf", b"\x1f\x8b", b"BZh", b"\xfd7zXZ", b"MSCF")
_EXT = re.compile(r"\.([A-Za-z0-9]{1,8})(?=\.|$)")
MAX_ZIP_NAMES = 2000


def _zip_kind(b: bytes) -> str:
    """Classify a ZIP container from its central directory names only (no extraction)."""
    try:
        with zipfile.ZipFile(io.BytesIO(b)) as z:
            names = z.namelist()[:MAX_ZIP_NAMES]
    except (zipfile.BadZipFile, ValueError, OSError):
        return "zip_malformed"
    low = [n.lower() for n in names]
    if any("vbaproject.bin" in n or n.endswith((".exe", ".dll", ".js", ".vbs", ".bat", ".ps1")) for n in low):
        return "zip_with_code"
    if "xl/workbook.xml" in low and not any(n.startswith(("xl/macrosheets", "xl/activex")) for n in low):
        return "xlsx"
    return "zip_other"


def classify(name: str, data: bytes) -> dict:
    """Return {"kind","route","blocked","reason","flags"}. route is a connector id or ""."""
    exts = [e.lower() for e in _EXT.findall(name or "")]
    flags = []
    if len(exts) > 1:
        flags.append("multiple_extensions")
    if data.startswith(b"PK\x03\x04") or data.startswith(b"PK\x05\x06"):
        kind = _zip_kind(data)
        if kind == "xlsx" and not any(e in EXEC_EXT for e in exts):
            return {"kind": "xlsx", "route": "discovery.tabular", "blocked": False, "reason": "", "flags": flags}
        if kind == "zip_with_code" or any(e in EXEC_EXT for e in exts):
            return {"kind": kind, "route": "", "blocked": True, "reason": "executable", "flags": flags}
        return {"kind": kind, "route": "", "blocked": True, "reason": "archive_unsupported", "flags": flags}
    for sig, label in EXEC_MAGIC:
        if data.startswith(sig):
            return {"kind": label, "route": "", "blocked": True, "reason": "executable", "flags": flags}
    if any(e in EXEC_EXT for e in exts):
        return {"kind": "by_extension", "route": "", "blocked": True, "reason": "executable", "flags": flags}
    if any(data.startswith(s) for s in ARCHIVE_MAGIC) or any(e in ARCHIVE_EXT for e in exts):
        return {"kind": "archive", "route": "", "blocked": True, "reason": "archive_unsupported", "flags": flags}
    try:
        kind = detect_type(data)
    except Int001UnsupportedType:
        kind = ""
    if kind:
        if exts and exts[-1] not in {kind, "jpg", "jpeg", "tif", "tiff"}:
            flags.append("extension_mismatch")
        return {"kind": kind, "route": "discovery.intake", "blocked": False, "reason": "", "flags": flags}
    head = data[:4096]
    if head and b"\x00" not in head and exts and exts[-1] in ("csv", "tsv", "txt"):
        return {"kind": "csv", "route": "discovery.tabular", "blocked": False, "reason": "", "flags": flags}
    return {"kind": "unknown", "route": "", "blocked": True, "reason": "unsupported_type", "flags": flags}
