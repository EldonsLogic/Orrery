"""Builders for the DSC-014 tests: minimal valid file bytes and a canned OCR engine. Synthetic only."""
import struct
import zlib

from connectors.intake import OcrResult, OcrToken


class FakeOcrEngine:
    """Returns canned tokens per page; records the hints it was called with."""

    def __init__(self, pages=None, language="ar"):
        self.pages = pages if pages is not None else [[]]
        self.language = language
        self.calls = []

    def recognise(self, image_bytes, hints):
        self.calls.append(dict(hints))
        toks = self.pages[min(hints["page"], len(self.pages)) - 1]
        return OcrResult(tuple(toks), self.language)


def tokens(lines, conf=0.97, overrides=None, start_line=0):
    """lines: list of strings (one token per whitespace word). overrides: {word: confidence}."""
    overrides = overrides or {}
    out = []
    for li, line in enumerate(lines, start_line):
        x = 10
        for w in line.split(" "):
            out.append(OcrToken(w, overrides.get(w, conf), (x, 20 * li, 8 * len(w) + 4, 14), li))
            x += 8 * len(w) + 10
    return out


def hidden(text, line, reason="white_on_white"):
    return [OcrToken(w, 0.9, (0, 1000, 5, 5), line, visible=False, hidden_reason=reason) for w in text.split(" ")]


def _chunk(typ, body):
    return struct.pack(">I", len(body)) + typ + body + struct.pack(">I", zlib.crc32(typ + body))


def png(w=100, h=50, text=None):
    out = b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    for k, v in (text or {}).items():
        out += _chunk(b"tEXt", k.encode() + b"\x00" + v.encode("latin-1"))
    return out + _chunk(b"IDAT", zlib.compress(b"\x00")) + _chunk(b"IEND", b"")


def _tiff_block(desc, w=100, h=50, endian="<"):
    ents = [(256, 4, 1, w), (257, 4, 1, h)]
    extra = b""
    n = 3 if desc else 2
    base = 8 + 2 + n * 12 + 4
    body = b""
    if desc:
        d = desc.encode() + b"\x00"
        ents.append((270, 2, len(d), base))
        extra = d
    for t, ty, c, v in ents:
        body += struct.pack(endian + "HHII", t, ty, c, v)
    return struct.pack(endian + "H", n) + body + struct.pack(endian + "I", 0) + extra


def tiff(pages=1, desc=None):
    out = b"II*\x00" + struct.pack("<I", 8)
    first = bytearray(_tiff_block(desc))
    if pages == 1:
        return out + bytes(first)
    # chain extra bare IFDs after the first one
    nfirst = len(first)
    cursor = 8 + nfirst
    off_pos = 2 + (3 if desc else 2) * 12
    first[off_pos:off_pos + 4] = struct.pack("<I", cursor)
    out += bytes(first)
    for i in range(1, pages):
        blk = bytearray(_tiff_block(None))
        nxt = cursor + len(blk) if i < pages - 1 else 0
        blk[2 + 2 * 12:2 + 2 * 12 + 4] = struct.pack("<I", nxt)
        out += bytes(blk)
        cursor += len(blk)
    return out


def jpeg(w=100, h=50, comment=None, exif_desc=None):
    out = b"\xff\xd8"
    if exif_desc:
        tb = b"II*\x00" + struct.pack("<I", 8) + _tiff_block_ascii_only(exif_desc)
        seg = b"Exif\x00\x00" + tb
        out += b"\xff\xe1" + struct.pack(">H", len(seg) + 2) + seg
    if comment:
        c = comment.encode()
        out += b"\xff\xfe" + struct.pack(">H", len(c) + 2) + c
    sof = struct.pack(">BHHB", 8, h, w, 1) + b"\x01\x11\x00"
    out += b"\xff\xc0" + struct.pack(">H", len(sof) + 2) + sof
    return out + b"\xff\xda\x00\x02" + b"\xff\xd9"


def _tiff_block_ascii_only(desc):
    d = desc.encode() + b"\x00"
    return struct.pack("<H", 1) + struct.pack("<HHII", 270, 2, len(d), 8 + 2 + 12 + 4) + struct.pack("<I", 0) + d


def pdf(pages=1, extra=b"", info=None, catalog_extra=b""):
    kids = " ".join(f"{3 + i} 0 R" for i in range(pages)).encode()
    body = b"%PDF-1.4\n1 0 obj\n<</Type/Catalog/Pages 2 0 R" + catalog_extra + b">>\nendobj\n"
    body += b"2 0 obj\n<</Type/Pages/Kids[" + kids + b"]/Count " + str(pages).encode() + b">>\nendobj\n"
    for i in range(pages):
        body += f"{3 + i} 0 obj\n<</Type/Page/Parent 2 0 R>>\nendobj\n".encode()
    if info:
        body += b"90 0 obj\n<<" + b"".join(b"/" + k.encode() + b"(" + v.encode() + b")" for k, v in info.items()) + b">>\nendobj\n"
    return body + extra + b"trailer\n<</Root 1 0 R>>\n%%EOF\n"
