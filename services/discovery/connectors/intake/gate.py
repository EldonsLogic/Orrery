"""File gate that runs before any OCR: magic-byte type, size, pages, dimensions from headers only,
PDF active-content refusal, and metadata capture. Nothing is decoded, rendered or executed here.
Design basis: docs/security/brand-asset-upload-security.md (BAU-001, BAU-011, BAU-021)."""
from __future__ import annotations

import re
import struct
import zlib

from .errors import (Int001UnsupportedType, Int002Oversize, Int003TooManyPages, Int004ImageTooLarge,
                     Int005Malformed, Int006ActiveContent, Int007Encrypted)

PNG_SIG = b"\x89PNG\r\n\x1a\n"
META_CAP = 2000
_NAME = re.compile(rb"/[A-Za-z0-9#_.\-]+")
_HEX = re.compile(rb"#([0-9A-Fa-f]{2})")
_DANGEROUS = re.compile(rb"/(JavaScript|JS|Launch|EmbeddedFiles?|RichMedia|XFA|SubmitForm|ImportData|"
                        rb"OpenAction|AA|GoToR|GoToE|Movie|Sound)(?![A-Za-z0-9#_.\-])")
_PAGE = re.compile(rb"/Type\s*/Page(?![A-Za-z0-9#_.\-])")
_INFO = re.compile(rb"/(Title|Author|Subject|Keywords|Creator|Producer)\s*\(((?:\\.|[^\\()])*)\)", re.S)
_STREAM = re.compile(rb"stream\r?\n(.*?)\r?\nendstream", re.S)


def detect_type(b: bytes) -> str:
    if b.startswith(b"%PDF-"):
        return "pdf"
    if b.startswith(PNG_SIG):
        return "png"
    if b.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if b[:4] in (b"II*\x00", b"MM\x00*"):
        return "tiff"
    raise Int001UnsupportedType("only PDF, PNG, JPEG and TIFF are accepted (decided by content)")


def _clip(s: str) -> str:
    return s if len(s) <= META_CAP else s[:META_CAP] + " [truncated]"


def _decode_text(b: bytes) -> str:
    if b.startswith(b"\xfe\xff"):
        return b[2:].decode("utf-16-be", "replace")
    return b.decode("utf-8", "replace") if b else ""


def _unname(blob: bytes) -> bytes:
    """Decode #xx escapes inside PDF names so /J#61vaScript is seen as /JavaScript."""
    return _NAME.sub(lambda m: _HEX.sub(lambda h: bytes([int(h.group(1), 16)]), m.group(0)), blob)


def _unescape_pdf_string(raw: bytes) -> bytes:
    out, i = bytearray(), 0
    esc = {ord("n"): 10, ord("r"): 13, ord("t"): 9, ord("b"): 8, ord("f"): 12}
    while i < len(raw):
        c = raw[i]
        if c == 0x5C and i + 1 < len(raw):
            n = raw[i + 1]
            if 0x30 <= n <= 0x37:
                j = i + 1
                while j < len(raw) and j < i + 4 and 0x30 <= raw[j] <= 0x37:
                    j += 1
                out.append(int(raw[i + 1:j], 8) & 255)
                i = j
                continue
            out.append(esc.get(n, n))
            i += 2
            continue
        out.append(c)
        i += 1
    return bytes(out)


def inspect_pdf(b: bytes, max_pages: int) -> dict:
    blob = _unname(b)
    if re.search(rb"/Encrypt(?![A-Za-z0-9#_.\-])", blob):
        raise Int007Encrypted("encrypted PDF")
    scan = [blob]
    budget_out, nstreams = 8_000_000, 0
    for m in _STREAM.finditer(blob):
        if b"/ObjStm" not in blob[max(0, m.start() - 400):m.start()]:
            continue
        nstreams += 1
        if nstreams > 200:
            raise Int005Malformed("too many object streams")
        d = zlib.decompressobj()
        try:
            out = d.decompress(m.group(1), 2_000_000)
        except zlib.error:
            continue
        if d.unconsumed_tail:
            raise Int005Malformed("object stream expands past the cap")
        budget_out -= len(out)
        if budget_out < 0:
            raise Int005Malformed("object streams expand past the cap")
        scan.append(_unname(out))
    found = sorted({m.group(1).decode() for s in scan for m in _DANGEROUS.finditer(s)})
    if found:
        raise Int006ActiveContent("active or embedded content: " + ", ".join(found))
    pages = sum(len(_PAGE.findall(s)) for s in scan)
    if pages == 0:
        raise Int005Malformed("no pages found")
    if pages > max_pages:
        raise Int003TooManyPages(f"{pages} pages, limit {max_pages}")
    meta = []
    for m in _INFO.finditer(blob):
        meta.append((m.group(1).decode(), _clip(_decode_text(_unescape_pdf_string(m.group(2))))))
    return {"pages": pages, "width": 0, "height": 0, "metadata": meta[:20]}


def _check_dims(w: int, h: int, max_side: int, max_pixels: int) -> None:
    if w <= 0 or h <= 0:
        raise Int005Malformed("zero image dimension")
    if w > max_side or h > max_side or w * h > max_pixels:
        raise Int004ImageTooLarge(f"{w}x{h} exceeds {max_side} per side or {max_pixels} pixels")


def inspect_png(b: bytes, max_side: int, max_pixels: int) -> dict:
    if len(b) < 33 or b[12:16] != b"IHDR" or struct.unpack(">I", b[8:12])[0] != 13:
        raise Int005Malformed("PNG header")
    w, h = struct.unpack(">II", b[16:24])
    _check_dims(w, h, max_side, max_pixels)
    meta, pos, n = [], 8, 0
    while pos + 12 <= len(b) and n < 2000:
        n += 1
        ln, typ = struct.unpack(">I", b[pos:pos + 4])[0], b[pos + 4:pos + 8]
        end = pos + 8 + ln
        if end + 4 > len(b):
            raise Int005Malformed("PNG chunk overruns file")
        body = b[pos + 8:end]
        if typ == b"tEXt" and b"\x00" in body:
            k, v = body.split(b"\x00", 1)
            meta.append((k.decode("latin-1")[:80], _clip(v.decode("latin-1"))))
        elif typ == b"iTXt" and body.count(b"\x00") >= 3:
            k, rest = body.split(b"\x00", 1)
            if rest[:1] == b"\x00":  # uncompressed only
                parts = rest[2:].split(b"\x00", 2)
                if len(parts) == 3:
                    meta.append((k.decode("latin-1")[:80], _clip(parts[2].decode("utf-8", "replace"))))
        elif typ == b"zTXt":
            meta.append((body.split(b"\x00", 1)[0].decode("latin-1")[:80], "[compressed text chunk not read]"))
        if typ == b"IEND":
            break
        pos = end + 4
    return {"pages": 1, "width": w, "height": h, "metadata": meta[:20]}


_TIFF_TAGS = {0x010E: "ImageDescription", 0x013B: "Artist", 0x8298: "Copyright", 0x0131: "Software",
              0x010D: "DocumentName", 0x0132: "DateTime", 0x010F: "Make", 0x0110: "Model"}
_TYPE_SIZE = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8}


def _tiff(b: bytes, max_pages: int, want_chain: bool) -> dict:
    if len(b) < 8:
        raise Int005Malformed("TIFF header")
    e = "<" if b[:2] == b"II" else ">"
    off = struct.unpack(e + "I", b[4:8])[0]
    pages, out, seen = 0, {"width": 0, "height": 0, "strings": []}, set()
    while off and off not in seen and pages <= max_pages:
        seen.add(off)
        if off + 2 > len(b):
            raise Int005Malformed("TIFF IFD out of range")
        n = struct.unpack(e + "H", b[off:off + 2])[0]
        if off + 2 + n * 12 + 4 > len(b) or n > 1000:
            raise Int005Malformed("TIFF IFD overruns file")
        for i in range(n):
            ent = b[off + 2 + i * 12: off + 14 + i * 12]
            tag, typ, cnt = struct.unpack(e + "HHI", ent[:8])
            size = _TYPE_SIZE.get(typ, 1) * cnt
            if size > len(b):
                raise Int005Malformed("TIFF entry too large")
            if size <= 4:
                data = ent[8:8 + size]
            else:
                p = struct.unpack(e + "I", ent[8:12])[0]
                if p + size > len(b):
                    raise Int005Malformed("TIFF entry out of range")
                data = b[p:p + size]
            if pages == 0:
                if tag in (256, 257) and typ in (3, 4) and cnt == 1:
                    v = struct.unpack(e + ("H" if typ == 3 else "I"), data[:_TYPE_SIZE[typ]])[0]
                    out["width" if tag == 256 else "height"] = v
                elif tag in _TIFF_TAGS and typ == 2:
                    out["strings"].append((_TIFF_TAGS[tag], _clip(data.split(b"\x00")[0].decode("utf-8", "replace"))))
        pages += 1
        off = struct.unpack(e + "I", b[off + 2 + n * 12: off + 6 + n * 12])[0]
        if not want_chain:
            break
    out["pages"] = pages
    return out


def inspect_tiff(b: bytes, max_pages: int, max_side: int, max_pixels: int) -> dict:
    t = _tiff(b, max_pages, True)
    if t["pages"] > max_pages:
        raise Int003TooManyPages(f"more than {max_pages} pages")
    _check_dims(t["width"], t["height"], max_side, max_pixels)
    return {"pages": t["pages"], "width": t["width"], "height": t["height"], "metadata": t["strings"][:20]}


def inspect_jpeg(b: bytes, max_side: int, max_pixels: int) -> dict:
    pos, meta, w, h, n = 2, [], 0, 0, 0
    while pos + 4 <= len(b) and n < 500:
        n += 1
        if b[pos] != 0xFF:
            raise Int005Malformed("JPEG marker")
        m = b[pos + 1]
        if m == 0xFF:
            pos += 1
            continue
        if m in (0xD8, 0x01) or 0xD0 <= m <= 0xD7:
            pos += 2
            continue
        ln = struct.unpack(">H", b[pos + 2:pos + 4])[0]
        if ln < 2 or pos + 2 + ln > len(b):
            raise Int005Malformed("JPEG segment overruns file")
        seg = b[pos + 4:pos + 2 + ln]
        if 0xC0 <= m <= 0xCF and m not in (0xC4, 0xC8, 0xCC):
            if len(seg) < 5:
                raise Int005Malformed("JPEG frame header")
            h, w = struct.unpack(">HH", seg[1:5])
            break
        if m == 0xFE:
            meta.append(("Comment", _clip(seg.decode("utf-8", "replace"))))
        elif m == 0xE1 and seg.startswith(b"Exif\x00\x00"):
            try:
                for k, v in _tiff(seg[6:], 1, False)["strings"]:
                    meta.append((k, v))
            except Int005Malformed:
                meta.append(("Exif", "[unreadable EXIF block discarded]"))
        elif m == 0xE1 and seg.startswith(b"http://ns.adobe.com/xap/1.0/"):
            meta.append(("XMP", _clip(seg[29:].decode("utf-8", "replace"))))
        if m == 0xDA:
            break
        pos += 2 + ln
    _check_dims(w, h, max_side, max_pixels)
    return {"pages": 1, "width": w, "height": h, "metadata": meta[:20]}


def gate(b: bytes, max_bytes: int, max_pages: int, max_side: int, max_pixels: int) -> dict:
    """Return {"kind", "pages", "width", "height", "metadata": [(key, text)]} or raise IntakeRefusal."""
    if len(b) > max_bytes:
        raise Int002Oversize(f"{len(b)} bytes, limit {max_bytes}")
    kind = detect_type(b)
    if kind == "pdf":
        info = inspect_pdf(b, max_pages)
    elif kind == "png":
        info = inspect_png(b, max_side, max_pixels)
    elif kind == "jpeg":
        info = inspect_jpeg(b, max_side, max_pixels)
    else:
        info = inspect_tiff(b, max_pages, max_side, max_pixels)
    info["kind"] = kind
    return info
