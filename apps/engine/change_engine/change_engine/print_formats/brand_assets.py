"""Tenant brand asset validation and sanitising for printed documents (ERP-016).

Applies the rules of docs/security/brand-asset-upload-security.md (SEC-018) at the point a logo
is embedded in a document: content decides the type, size and dimension limits, polyglots and
trailing data are rejected, rasters are rebuilt from their critical chunks (all metadata dropped)
and SVG goes through an allow-list walker that re-serialises from the parsed tree, so nothing from
the upload text survives. Anything unsafe is removed and listed in ``SanitizedLogo.changes`` for
the audit trail; if nothing safe remains the logo is rejected (fail closed).

This is the last line of defence, not the upload pipeline: the malware scan, sandboxed decoder,
EXIF orientation handling and storage rules belong to BRD-007 and SEC-006. Documents embed the
result with ``<img>`` only, never as inline markup.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
import hashlib
import math
import re
import struct
from typing import Any
import unicodedata
import xml.etree.ElementTree as ET
import zlib

MAX_RASTER_BYTES = 2 * 1024 * 1024
MAX_SVG_BYTES = 200 * 1024
MAX_RASTER_SIDE = 4096
MAX_RASTER_PIXELS = 16_000_000
MAX_SVG_ELEMENTS = 5000
MAX_SVG_DEPTH = 32
MAX_SVG_USES = 16

_SVG_NS = "http://www.w3.org/2000/svg"
_XLINK_NS = "http://www.w3.org/1999/xlink"
_DATA_URI_RE = re.compile(r"^data:([A-Za-z]+/[A-Za-z0-9.+-]+);base64,([A-Za-z0-9+/=\s]*)$")
_ALLOWED_MIMES = {
    "image/png": "image/png",
    "image/jpeg": "image/jpeg",
    "image/jpg": "image/jpeg",
    "image/svg+xml": "image/svg+xml",
}
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_PNG_KEEP = {b"IHDR", b"PLTE", b"tRNS", b"IDAT", b"IEND"}
_PNG_APNG = {b"acTL", b"fcTL", b"fdAT"}

_SVG_ELEMENTS = frozenset({
    "svg", "g", "defs", "path", "rect", "circle", "ellipse", "line", "polyline", "polygon",
    "text", "tspan", "linearGradient", "radialGradient", "stop", "clipPath", "mask",
    "symbol", "use",
})
_SVG_DRAWABLE = frozenset(
    {"path", "rect", "circle", "ellipse", "line", "polyline", "polygon", "text"}
)
_SVG_ATTRIBUTES = frozenset({
    "d", "x", "y", "cx", "cy", "r", "rx", "ry", "x1", "y1", "x2", "y2", "fx", "fy", "points",
    "width", "height", "viewBox", "preserveAspectRatio", "transform", "fill", "fill-opacity",
    "fill-rule", "stroke", "stroke-width", "stroke-opacity", "stroke-linecap",
    "stroke-linejoin", "stroke-miterlimit", "stroke-dasharray", "stroke-dashoffset", "opacity",
    "stop-color", "stop-opacity", "offset", "gradientUnits", "gradientTransform",
    "spreadMethod", "clip-path", "mask", "clip-rule", "font-size", "font-weight", "text-anchor",
    "direction", "lang", "id", "dx", "dy", "clipPathUnits", "maskUnits", "href",
})
# Characters a safe attribute value may contain. Colons, quotes, angle brackets, backslashes,
# "@" and ";" are excluded, which on its own removes "javascript:", "data:", "http://" and
# "@import"; "url(" is additionally limited to same-document fragments below.
_SAFE_VALUE_RE = re.compile(r"^[\w\s.,+\-%#()]*$")
_URL_FRAGMENT_RE = re.compile(r"url\(\s*#[A-Za-z_][\w.\-]*\s*\)", re.IGNORECASE)
_ID_RE = re.compile(r"^[A-Za-z_][\w.\-]{0,63}$")
_BANNED_VALUE_PARTS = ("expression(", "javascript", "vbscript")
_DOCTYPE_RE = re.compile(r"<!\s*(doctype|entity|element|attlist|notation)", re.IGNORECASE)
_BIDI_CONTROLS = set("‪‫‬‭‮⁦⁧⁨⁩")


class BrandAssetError(ValueError):
    """A brand asset was rejected; the message names the reason and never any internals."""


@dataclass(frozen=True)
class SanitizedLogo:
    data_uri: str
    mime: str
    sha256: str
    changes: tuple[str, ...] = ()
    width: int | None = None
    height: int | None = None


def sanitize_brand_logo(source: str | bytes) -> SanitizedLogo:
    """Validate and sanitise a logo given as a base64 data URI, SVG markup or raw bytes."""
    declared: str | None = None
    if isinstance(source, (bytes, bytearray)):
        raw = bytes(source)
    elif isinstance(source, str):
        stripped = source.strip()
        if stripped.lower().startswith("data:"):
            match = _DATA_URI_RE.fullmatch(stripped)
            if not match:
                raise BrandAssetError("Logo must be a base64 PNG, JPEG or SVG data URI")
            declared = _ALLOWED_MIMES.get(match.group(1).lower())
            if declared is None:
                raise BrandAssetError("Logo type not allowed; only PNG, JPEG and SVG are accepted")
            body = re.sub(r"\s+", "", match.group(2))
            if len(body) > (MAX_RASTER_BYTES * 4) // 3 + 8:
                raise BrandAssetError("Logo exceeds the size limit")
            try:
                raw = base64.b64decode(body, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise BrandAssetError("Logo payload is not valid base64") from exc
        elif stripped.startswith("<"):
            raw = stripped.encode("utf-8")
        else:
            raise BrandAssetError("Logo must be embedded data; external URLs are forbidden")
    else:
        raise BrandAssetError("Logo must be a data URI string or bytes")

    if not raw:
        raise BrandAssetError("Logo is empty")

    sniffed = _sniff(raw)
    if declared is not None and declared != sniffed:
        raise BrandAssetError("Logo content does not match its declared type")

    if sniffed == "image/png":
        _check_size(raw, MAX_RASTER_BYTES)
        out, changes, size = _rebuild_png(raw)
    elif sniffed == "image/jpeg":
        _check_size(raw, MAX_RASTER_BYTES)
        out, changes, size = _rebuild_jpeg(raw)
    else:
        _check_size(raw, MAX_SVG_BYTES)
        out, changes = _sanitize_svg(raw)
        size = (None, None)
    return SanitizedLogo(
        data_uri=f"data:{sniffed};base64,{base64.b64encode(out).decode('ascii')}",
        mime=sniffed,
        sha256=hashlib.sha256(out).hexdigest(),
        changes=tuple(changes),
        width=size[0],
        height=size[1],
    )


def _check_size(raw: bytes, limit: int) -> None:
    if len(raw) > limit:
        raise BrandAssetError(f"Logo exceeds the {limit // 1024} KB size limit")


def _sniff(raw: bytes) -> str:
    if raw.startswith(_PNG_SIGNATURE):
        return "image/png"
    if raw.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    head = raw[:512].lstrip(b"\xef\xbb\xbf \t\r\n")
    if head.startswith(b"<"):
        return "image/svg+xml"
    raise BrandAssetError("Logo content is not a PNG, JPEG or SVG")


def _check_dimensions(width: int, height: int) -> None:
    if width < 1 or height < 1 or width > MAX_RASTER_SIDE or height > MAX_RASTER_SIDE:
        raise BrandAssetError(f"Logo dimensions must be 1 to {MAX_RASTER_SIDE} px per side")
    if width * height > MAX_RASTER_PIXELS:
        raise BrandAssetError("Logo has too many pixels")
    if max(width, height) / min(width, height) > 8:
        raise BrandAssetError("Logo aspect ratio must be at most 8:1")


# ------------------------------------------------------------------ PNG
def _rebuild_png(raw: bytes) -> tuple[bytes, list[str], tuple[int, int]]:
    pos = len(_PNG_SIGNATURE)
    kept: list[tuple[bytes, bytes]] = []
    dropped: list[str] = []
    width = height = 0
    idat = bytearray()
    seen_iend = False
    first = True
    while pos < len(raw):
        if seen_iend:
            raise BrandAssetError("Logo has data after the PNG end marker")
        if pos + 12 > len(raw):
            raise BrandAssetError("PNG is truncated")
        length = struct.unpack(">I", raw[pos:pos + 4])[0]
        kind = raw[pos + 4:pos + 8]
        end = pos + 8 + length
        if not re.fullmatch(rb"[A-Za-z]{4}", kind) or end + 4 > len(raw):
            raise BrandAssetError("PNG chunk is malformed")
        data = raw[pos + 8:end]
        crc = struct.unpack(">I", raw[end:end + 4])[0]
        if zlib.crc32(kind + data) & 0xFFFFFFFF != crc:
            raise BrandAssetError("PNG checksum failed")
        if first and kind != b"IHDR":
            raise BrandAssetError("PNG must start with a header chunk")
        first = False
        if kind in _PNG_APNG:
            raise BrandAssetError("Animated PNG is not allowed")
        if kind == b"IHDR":
            if length != 13:
                raise BrandAssetError("PNG header is malformed")
            width, height = struct.unpack(">II", data[:8])
            _check_dimensions(width, height)
        if kind == b"IDAT":
            idat += data
        if kind == b"IEND":
            if length:
                raise BrandAssetError("PNG end marker is malformed")
            seen_iend = True
        if kind in _PNG_KEEP:
            if kind != b"IDAT":
                kept.append((kind, data))
        else:
            dropped.append(kind.decode("ascii"))
        pos = end + 4
    if not seen_iend or not idat or not width:
        raise BrandAssetError("PNG is incomplete")
    bound = width * height * 8 + height + 4096
    decoder = zlib.decompressobj()
    try:
        decoder.decompress(bytes(idat), bound)
    except zlib.error as exc:
        raise BrandAssetError("PNG image data is corrupt") from exc
    if decoder.unconsumed_tail:
        raise BrandAssetError("PNG image data expands beyond its declared size")
    out = bytearray(_PNG_SIGNATURE)
    for kind, data in kept:
        if kind == b"IEND":
            out += _png_chunk(b"IDAT", bytes(idat))
        out += _png_chunk(kind, data)
    changes = [f"dropped PNG chunk {name}" for name in dropped]
    return bytes(out), changes, (width, height)


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data)) + kind + data
        + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    )


# ------------------------------------------------------------------ JPEG
_JPEG_KEEP = {0xDB, 0xC4, 0xDD}  # DQT, DHT, DRI
_JPEG_SOF = {m for m in range(0xC0, 0xD0) if m not in (0xC4, 0xC8, 0xCC)}


def _rebuild_jpeg(raw: bytes) -> tuple[bytes, list[str], tuple[int, int]]:
    out = bytearray(b"\xff\xd8")
    changes: list[str] = []
    pos = 2
    size: tuple[int, int] | None = None
    scans = 0
    while True:
        if pos + 2 > len(raw) or raw[pos] != 0xFF:
            raise BrandAssetError("JPEG is malformed")
        while pos < len(raw) and raw[pos] == 0xFF:
            pos += 1
        marker = raw[pos]
        pos += 1
        if marker == 0xD9:
            if pos != len(raw):
                raise BrandAssetError("Logo has data after the JPEG end marker")
            break
        if marker in range(0xD0, 0xD8) or marker in (0x01, 0x00):
            raise BrandAssetError("JPEG is malformed")
        if pos + 2 > len(raw):
            raise BrandAssetError("JPEG is truncated")
        seg_len = struct.unpack(">H", raw[pos:pos + 2])[0]
        if seg_len < 2 or pos + seg_len > len(raw):
            raise BrandAssetError("JPEG segment is malformed")
        segment = raw[pos:pos + seg_len]
        pos += seg_len
        if marker in _JPEG_SOF:
            if seg_len < 8:
                raise BrandAssetError("JPEG header is malformed")
            height, width = struct.unpack(">HH", segment[3:7])
            _check_dimensions(width, height)
            size = (width, height)
            out += bytes((0xFF, marker)) + segment
        elif marker in _JPEG_KEEP:
            out += bytes((0xFF, marker)) + segment
        elif marker == 0xDA:
            out += b"\xff\xda" + segment
            start = pos
            while True:
                nxt = raw.find(b"\xff", pos)
                if nxt < 0 or nxt + 1 >= len(raw):
                    raise BrandAssetError("JPEG is truncated")
                follow = raw[nxt + 1]
                if follow == 0x00 or follow in range(0xD0, 0xD8) or follow == 0xFF:
                    pos = nxt + 2 if follow != 0xFF else nxt + 1
                    continue
                pos = nxt
                break
            out += raw[start:pos]
            scans += 1
        else:
            changes.append(f"dropped JPEG segment 0xFF{marker:02X}")
    if size is None or not scans:
        raise BrandAssetError("JPEG is incomplete")
    out += b"\xff\xd9"
    return bytes(out), changes, size


# ------------------------------------------------------------------ SVG
def _local(tag: Any) -> tuple[str, str]:
    if not isinstance(tag, str):
        return "", ""
    if tag.startswith("{"):
        ns, _, name = tag[1:].partition("}")
        return ns, name
    return "", tag


def _clean_text(text: str | None) -> str:
    value = text or ""
    for ch in value:
        if ch in _BIDI_CONTROLS or (unicodedata.category(ch) == "Cc" and ch not in "\n\t\r"):
            raise BrandAssetError("SVG text contains control or bidirectional override characters")
    return value


def _sanitize_svg(raw: bytes) -> tuple[bytes, list[str]]:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise BrandAssetError("SVG must be UTF-8") from exc
    if _DOCTYPE_RE.search(text):
        raise BrandAssetError("SVG must not declare a DOCTYPE or entities")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise BrandAssetError("SVG is not well-formed XML") from exc
    if _local(root.tag) != (_SVG_NS, "svg"):
        raise BrandAssetError("SVG root element must be <svg> in the SVG namespace")

    count = 0
    stack = [(root, 1)]
    while stack:
        node, depth = stack.pop()
        count += 1
        if count > MAX_SVG_ELEMENTS or depth > MAX_SVG_DEPTH:
            raise BrandAssetError("SVG is too large or too deeply nested")
        stack.extend((child, depth + 1) for child in node)

    changes: list[str] = []
    clean_root = _clean_element(root, changes, is_root=True)
    assert clean_root is not None
    ids = {e.get("id"): e for e in clean_root.iter() if e.get("id")}
    uses = [e for e in clean_root.iter("use")]
    if len(uses) > MAX_SVG_USES:
        raise BrandAssetError("SVG has too many <use> references")
    for use in uses:
        target = use.get("href", "")[1:]
        if target not in ids:
            changes.append("removed <use> with a missing target")
            _remove(clean_root, use)
    _reject_use_cycles(clean_root)

    view_box = _resolve_view_box(root, clean_root)
    clean_root.set("viewBox", view_box)
    for key in ("width", "height"):
        clean_root.attrib.pop(key, None)
    if not any(e.tag in _SVG_DRAWABLE for e in clean_root.iter()):
        raise BrandAssetError("Nothing safe remains in the SVG after sanitising")

    serialised = _serialise(clean_root).encode("utf-8")
    if len(serialised) > MAX_SVG_BYTES:
        raise BrandAssetError("Sanitised SVG exceeds the size limit")
    again_root = ET.fromstring(serialised)
    again = _clean_element(again_root, [], is_root=True)
    if again is None or _serialise(again).encode("utf-8") != serialised:
        raise BrandAssetError("SVG could not be sanitised to a stable form")
    return serialised, changes


def _clean_element(node: ET.Element, changes: list[str], *, is_root: bool = False):
    ns, name = _local(node.tag)
    if ns != _SVG_NS or name not in _SVG_ELEMENTS:
        changes.append(f"removed <{name or 'unknown'}>")
        return None
    clean = ET.Element(name)
    for key, value in node.attrib.items():
        attr_ns, attr_name = _local(key)
        if attr_ns not in ("", _XLINK_NS) or (attr_ns == _XLINK_NS and attr_name != "href"):
            changes.append(f"removed attribute {attr_name}")
            continue
        if attr_name not in _SVG_ATTRIBUTES:
            changes.append(f"removed attribute {attr_name}")
            continue
        value = _clean_text(value)
        if not _attribute_safe(attr_name, value):
            changes.append(f"removed unsafe attribute {attr_name}")
            continue
        clean.set(attr_name, value.strip())
    if name == "use":
        href = clean.get("href", "")
        if not re.fullmatch(r"#[A-Za-z_][\w.\-]*", href):
            changes.append("removed <use> with a non-local reference")
            return None
    if name in ("text", "tspan"):
        clean.text = _clean_text(node.text)
    for child in node:
        clean_child = _clean_element(child, changes)
        if clean_child is not None:
            clean.append(clean_child)
        if name in ("text", "tspan") and child.tail:
            clean_child_tail = _clean_text(child.tail)
            if clean_child is not None:
                clean_child.tail = clean_child_tail
    return clean


def _attribute_safe(name: str, value: str) -> bool:
    if len(value) > 8192 or not _SAFE_VALUE_RE.fullmatch(value):
        return False
    folded = re.sub(r"\s+", "", value.lower())
    if any(part in folded for part in _BANNED_VALUE_PARTS):
        return False
    if "url(" in folded:
        if name not in ("fill", "stroke", "clip-path", "mask"):
            return False
        if "url(" in re.sub(r"\s+", "", _URL_FRAGMENT_RE.sub("", value).lower()):
            return False
    if name == "id":
        return bool(_ID_RE.fullmatch(value))
    if name == "href":
        return bool(re.fullmatch(r"#[A-Za-z_][\w.\-]*", value))
    return True


def _remove(root: ET.Element, target: ET.Element) -> None:
    for parent in root.iter():
        for child in list(parent):
            if child is target:
                parent.remove(child)
                return


def _reject_use_cycles(root: ET.Element) -> None:
    by_id = {e.get("id"): e for e in root.iter() if e.get("id")}

    def walk(element: ET.Element, trail: tuple[str, ...]) -> None:
        for node in element.iter():
            if node.tag != "use":
                continue
            target_id = node.get("href", "")[1:]
            if target_id in trail:
                raise BrandAssetError("SVG <use> references form a loop")
            target = by_id.get(target_id)
            if target is not None:
                walk(target, trail + (target_id,))

    for use in root.iter("use"):
        target_id = use.get("href", "")[1:]
        target = by_id.get(target_id)
        if target is None:
            continue
        # A use inside its own target (directly or transitively) is a loop.
        if any(inner is use for inner in target.iter()):
            raise BrandAssetError("SVG <use> references form a loop")
        walk(target, (target_id,))


def _resolve_view_box(original: ET.Element, clean_root: ET.Element) -> str:
    candidate = clean_root.get("viewBox")
    parts = _numbers(candidate) if candidate else None
    if parts and len(parts) == 4 and parts[2] > 0 and parts[3] > 0:
        return " ".join(_num(p) for p in parts)
    width = _numbers(original.get("width", ""))
    height = _numbers(original.get("height", ""))
    if width and height and len(width) == len(height) == 1 and width[0] > 0 and height[0] > 0:
        return f"0 0 {_num(width[0])} {_num(height[0])}"
    raise BrandAssetError("SVG needs a valid viewBox")


def _numbers(value: str | None) -> list[float] | None:
    if not value:
        return None
    try:
        nums = [float(p) for p in re.split(r"[\s,]+", value.strip()) if p]
    except ValueError:
        return None
    return nums if all(math.isfinite(n) and abs(n) < 1e7 for n in nums) else None


def _num(value: float) -> str:
    return str(int(value)) if value == int(value) else repr(value)


def _escape(value: str) -> str:
    return (
        value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _serialise(element: ET.Element, *, is_root: bool = True) -> str:
    attrs = "".join(f' {k}="{_escape(v)}"' for k, v in element.attrib.items())
    if is_root:
        attrs = f' xmlns="{_SVG_NS}"' + attrs
    inner = _escape(element.text or "") + "".join(
        _serialise(child, is_root=False) + _escape(child.tail or "") for child in element
    )
    if not inner:
        return f"<{element.tag}{attrs}/>"
    return f"<{element.tag}{attrs}>{inner}</{element.tag}>"
