"""Hand-rolled, hardened OOXML (.xlsx) reader. Stdlib only, nothing evaluated, nothing fetched.

Refuses: macros, encryption, zip64, nested archives, path traversal, zip bombs, DOCTYPE/ENTITY.
"""
from __future__ import annotations

import io
import re
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from posixpath import normpath

from ..model import Budget, BudgetExceeded
from .common import detect_header_row, idx_to_col, split_ref
from .errors import (Tab001UnsupportedFormat, Tab002Encrypted, Tab003UnsafeArchive, Tab004DtdRefused,
                     Tab005MacroRefused, Tab006Malformed)

MAX_ENTRIES = 200
MAX_PART_BYTES = 25_000_000
MAX_TOTAL_BYTES = 40_000_000
MAX_RATIO = 100  # applied once an entry or the archive exceeds 1 MB uncompressed
MAX_XML_DEPTH = 64
MAX_SHARED_STRINGS = 200_000
MAX_SHARED_CHARS = 5_000_000
MAX_SHEET_NAME = 31  # Excel's own limit
MAX_DEFINED_NAME = 255
MAX_LIST = 20  # row/column numbers listed per hidden report
ARCHIVE_EXT = (".zip", ".jar", ".7z", ".rar", ".gz", ".tar", ".xlsx", ".xlsm", ".docx", ".pptx")
ARCHIVE_MAGIC = (b"PK\x03\x04", b"PK\x05\x06", b"\xd0\xcf\x11\xe0", b"\x1f\x8b", b"7z\xbc\xaf", b"Rar!")
BUILTIN_DATE_IDS = {14, 15, 16, 17, 22}  # clearly dates; 18-21 and 45-47 are time-only so stay numbers
_DT_ENC = re.compile(rb"""^\s*(?:\xef\xbb\xbf)?<\?xml[^>]*encoding\s*=\s*["']([^"']+)["']""", re.I)


def _ln(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def check_xml_bytes(data: bytes) -> None:
    """Refuse DTDs and entities before the parser sees them; refuse encodings that could hide them."""
    if data.startswith((b"\xff\xfe", b"\xfe\xff")) or b"\x00" in data:
        raise Tab004DtdRefused("non UTF-8 XML refused (could hide a DOCTYPE)")
    m = _DT_ENC.match(data[:300])
    if m and m.group(1).lower() not in (b"utf-8", b"utf8"):
        raise Tab004DtdRefused("non UTF-8 XML declaration refused")
    low = data.lower()
    if b"<!doctype" in low or b"<!entity" in low:
        raise Tab004DtdRefused("DOCTYPE or ENTITY in XML")


def iter_xml(data: bytes, budget: Budget):
    """Yield (event, element); ticks the budget per element and caps depth."""
    check_xml_bytes(data)
    depth = 0
    try:
        for ev, el in ET.iterparse(io.BytesIO(data), events=("start", "end")):
            if ev == "start":
                budget.tick()
                depth += 1
                if depth > MAX_XML_DEPTH:
                    raise Tab006Malformed("XML nested too deeply")
            else:
                depth -= 1
            yield ev, el
    except ET.ParseError as e:
        raise Tab006Malformed(f"xml: {e}") from None


def parse_small(data: bytes, budget: Budget):
    root = None
    for _ev, el in iter_xml(data, budget):
        if root is None:
            root = el
    if root is None:
        raise Tab006Malformed("empty XML part")
    return root


def _text(el) -> str:
    """Text of an <si>/<is>/<text>: <t> and rich-run <r><t>, never phonetic runs."""
    out = []
    for ch in el:
        n = _ln(ch.tag)
        if n == "t":
            out.append(ch.text or "")
        elif n == "r":
            out.extend((t.text or "") for t in ch if _ln(t.tag) == "t")
    return "".join(out)


def _has_zip64_extra(extra: bytes) -> bool:
    i = 0
    while i + 4 <= len(extra):
        hid = int.from_bytes(extra[i:i + 2], "little")
        ln = int.from_bytes(extra[i + 2:i + 4], "little")
        if hid == 0x0001:
            return True
        i += 4 + ln
    return False


class Package:
    def __init__(self, data: bytes, budget: Budget):
        self.budget = budget
        try:
            self.z = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile:
            raise Tab006Malformed("not a valid zip") from None
        self.read_total = 0
        self.names = []
        self._inspect(len(data))

    def _inspect(self, compressed_total: int) -> None:
        infos = self.z.infolist()
        if len(infos) > MAX_ENTRIES:
            raise Tab003UnsafeArchive(f"more than {MAX_ENTRIES} entries")
        seen, total = set(), 0
        for zi in infos:
            self.budget.tick()
            n = zi.filename
            if (not n or n.startswith("/") or "\\" in n or "\x00" in n or ":" in n or ".." in n.split("/")
                    or len(n) > 255):
                raise Tab003UnsafeArchive("path traversal or unsafe entry name")
            if n in seen:
                raise Tab003UnsafeArchive("duplicate entry name")
            seen.add(n)
            if zi.flag_bits & 0x1:
                raise Tab002Encrypted("encrypted zip entry")
            if zi.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                raise Tab003UnsafeArchive("unsupported compression method")
            if zi.file_size >= 0xFFFFFFFF or zi.compress_size >= 0xFFFFFFFF or _has_zip64_extra(zi.extra):
                raise Tab003UnsafeArchive("zip64 entries are refused")
            if zi.file_size > MAX_PART_BYTES:
                raise Tab003UnsafeArchive("entry too large")
            if zi.file_size > 1_000_000 and zi.file_size > MAX_RATIO * max(zi.compress_size, 1):
                raise Tab003UnsafeArchive("compression ratio too high (zip bomb)")
            total += zi.file_size
            low = n.lower()
            if "vbaproject" in low or low.startswith("xl/vba"):
                raise Tab005MacroRefused("VBA project present")
            if low.endswith(ARCHIVE_EXT) or low.startswith(("xl/embeddings/", "xl/activex/")):
                raise Tab003UnsafeArchive("nested archive or embedded object")
            self.names.append(n)
        if total > MAX_TOTAL_BYTES or (total > 1_000_000 and total > MAX_RATIO * max(compressed_total, 1)):
            raise Tab003UnsafeArchive("uncompressed size too large (zip bomb)")
        for zi in infos:  # nested archive by content, not just by name
            if zi.file_size >= 4 and not zi.is_dir():
                with self.z.open(zi) as f:
                    head = f.read(4)
                if head.startswith(ARCHIVE_MAGIC):
                    raise Tab003UnsafeArchive("nested archive")

    def has(self, name: str) -> bool:
        return name in self.names

    def read(self, name: str) -> bytes:
        try:
            zi = self.z.getinfo(name)
        except KeyError:
            raise Tab006Malformed(f"missing part {name}") from None
        with self.z.open(zi) as f:
            data = f.read(MAX_PART_BYTES + 1)  # real size, not the declared one
        if len(data) > MAX_PART_BYTES:
            raise Tab003UnsafeArchive("entry larger than allowed (zip bomb)")
        self.read_total += len(data)
        if self.read_total > MAX_TOTAL_BYTES:
            raise Tab003UnsafeArchive("uncompressed size too large (zip bomb)")
        return data


def _rels(pkg: Package, part: str):
    """Relationships of a part: [(id, type_suffix, resolved_target, external)]."""
    d, _, base = part.rpartition("/")
    rp = f"{d}/_rels/{base}.rels" if d else f"_rels/{base}.rels"
    if not pkg.has(rp):
        return []
    out = []
    for ev, el in iter_xml(pkg.read(rp), pkg.budget):
        if ev == "end" and _ln(el.tag) == "Relationship":
            ext = el.get("TargetMode", "").lower() == "external"
            tgt = el.get("Target", "")
            if not ext:
                tgt = normpath(tgt[1:] if tgt.startswith("/") else (f"{d}/{tgt}" if d else tgt))
                if tgt.startswith("..") or tgt.startswith("/"):
                    raise Tab003UnsafeArchive("relationship target escapes the package")
            out.append((el.get("Id", ""), (el.get("Type", "") or "").rsplit("/", 1)[-1], tgt, ext))
    return out


_STRIP = re.compile(r'"[^"]*"|\[[^\]]*\]|\\.|_.|\*.')


def _fmt_kind(code: str) -> str:
    c = _STRIP.sub("", code.split(";")[0]).lower()
    if "y" in c or "d" in c:
        return "datetime" if ("h" in c or "s" in c) else "date"
    return ""  # time-only, general, text, numbers: stay raw


_WHITE = {"FFFFFFFF", "FFFFFF", "00FFFFFF"}
MIN_FONT_SZ = 4.0  # points; smaller text is treated as hidden
MIN_COL_WIDTH = 0.5  # characters; narrower columns are treated as hidden


def _fmt_blank(code: str) -> bool:
    """True when every section of a number format is empty (e.g. ';;;'): the cell shows nothing."""
    return ";" in code and all(not _STRIP.sub("", sec).strip() for sec in code.split(";"))


def _white(color) -> bool:
    if color is None:
        return False
    rgb = (color.get("rgb") or "").upper()
    return rgb in _WHITE or (color.get("theme") == "0" and not color.get("tint"))


def _styles(pkg: Package):
    """cellXfs index -> date kind, and index -> hidden reason (blank number format, tiny or
    background-coloured font). Returns (date_xf, hide_xf)."""
    if not pkg.has("xl/styles.xml"):
        return {}, {}
    root = parse_small(pkg.read("xl/styles.xml"), pkg.budget)
    custom, xfs, fonts, fills = {}, [], [], []
    for ch in root:
        n = _ln(ch.tag)
        if n == "numFmts":
            for f in ch:
                custom[f.get("numFmtId", "")] = f.get("formatCode", "")
        elif n == "cellXfs":
            xfs = [(x.get("numFmtId", "0"), x.get("fontId", "0"), x.get("fillId", "0")) for x in ch]
        elif n == "fonts":
            for f in ch:
                sz = col = None
                for a in f:
                    if _ln(a.tag) == "sz":
                        try:
                            sz = float(a.get("val", ""))
                        except ValueError:
                            sz = None
                    elif _ln(a.tag) == "color":
                        col = a
                fonts.append((sz, _white(col)))
        elif n == "fills":
            for f in ch:
                light = True
                for pf in f:
                    if _ln(pf.tag) == "patternFill" and pf.get("patternType") == "solid":
                        fg = next((c for c in pf if _ln(c.tag) == "fgColor"), None)
                        light = fg is None or _white(fg) or not (fg.get("rgb") or fg.get("theme") or fg.get("indexed"))
                fills.append(light)
    out, hide = {}, {}
    for i, (fid, font_id, fill_id) in enumerate(xfs):
        if fid in custom:
            kind = _fmt_kind(custom[fid])
            if _fmt_blank(custom[fid]):
                hide[i] = "format_hidden"
        elif fid.isdigit() and int(fid) in BUILTIN_DATE_IDS:
            kind = "datetime" if fid == "22" else "date"
        else:
            kind = ""
        if kind:
            out[i] = kind
        if i not in hide and font_id.isdigit() and int(font_id) < len(fonts):
            sz, white = fonts[int(font_id)]
            light_bg = fills[int(fill_id)] if fill_id.isdigit() and int(fill_id) < len(fills) else True
            if (sz is not None and sz < MIN_FONT_SZ) or (white and light_bg):
                hide[i] = "font_hidden"
    return out, hide


def _iso(serial: str, kind: str, date1904: bool):
    try:
        v = float(serial)
    except ValueError:
        return None
    if not (v == v) or v < 61 or v >= 2958466:  # < 61: the 1900 leap-year bug zone, stays raw
        return None
    base = datetime(1904, 1, 1) if date1904 else datetime(1899, 12, 30)
    days = int(v)
    secs = round((v - days) * 86400)
    dt = base + timedelta(days=days, seconds=secs)
    return dt.strftime("%Y-%m-%dT%H:%M:%S") if kind == "datetime" and secs else dt.strftime("%Y-%m-%d")


def _shared(pkg: Package):
    if not pkg.has("xl/sharedStrings.xml"):
        return []
    out, chars = [], 0
    for ev, el in iter_xml(pkg.read("xl/sharedStrings.xml"), pkg.budget):
        if ev == "end" and _ln(el.tag) == "si":
            t = _text(el)
            chars += len(t)
            if len(out) >= MAX_SHARED_STRINGS or chars > MAX_SHARED_CHARS:
                raise BudgetExceeded("shared_strings", MAX_SHARED_STRINGS)
            out.append(t)
            el.clear()
    return out


def _comments(pkg: Package, target: str):
    out = []
    root = parse_small(pkg.read(target), pkg.budget)
    for el in root.iter():
        if _ln(el.tag) in ("comment", "threadedComment") and el.get("ref"):
            if not split_ref(el.get("ref")):
                raise Tab006Malformed("bad comment cell reference")
            for ch in el:
                if _ln(ch.tag) == "text":
                    t = _text(ch) if any(_ln(c.tag) in ("t", "r") for c in ch) else (ch.text or "")
                    if t:
                        out.append({"ref": el.get("ref"), "text": t})
    return out


def _ranges(nums):
    nums = sorted(set(nums))
    out, i = [], 0
    while i < len(nums) and len(out) < MAX_LIST:
        j = i
        while j + 1 < len(nums) and nums[j + 1] == nums[j] + 1:
            j += 1
        out.append(str(nums[i]) if i == j else f"{nums[i]}-{nums[j]}")
        i = j + 1
    return out


def _sheet(pkg: Package, target: str, name: str, state: str, shared, date_xf, hide_xf, date1904,
           max_rows: int, max_cols: int, max_cells: int) -> dict:
    cols_hidden, hidden_rows, hidden_cols, cells = [], [], set(), []
    row_no = col_no = ncells = 0
    row_reason = ""
    for ev, el in iter_xml(pkg.read(target), pkg.budget):
        n = _ln(el.tag)
        if ev == "start":
            if n == "row":
                row_no = int(el.get("r")) if (el.get("r") or "").isdigit() else row_no + 1
                if row_no > max_rows:
                    raise BudgetExceeded("rows", max_rows)
                row_reason = "hidden_row" if el.get("hidden", "") in ("1", "true") else ""
                if not row_reason and el.get("customHeight", "") in ("1", "true"):
                    try:
                        row_reason = "zero_height_row" if float(el.get("ht", "")) < 1 else ""
                    except ValueError:
                        pass
                if row_reason:
                    hidden_rows.append(row_no)
                col_no = 0
            continue
        if n == "col":  # <cols> is read wherever it sits (X4); reasons are applied after the pass
            reason = "hidden_column" if el.get("hidden", "") in ("1", "true") else ""
            if not reason:
                try:
                    reason = "zero_width_column" if float(el.get("width", "")) < MIN_COL_WIDTH else ""
                except ValueError:
                    pass
            if reason and (el.get("min") or "").isdigit() and (el.get("max") or "").isdigit():
                cols_hidden.append((int(el.get("min")), min(int(el.get("max")), max_cols), reason))
        elif n == "row":
            el.clear()
        elif n == "c":
            ref = el.get("r", "")
            sp = split_ref(ref)
            if sp:
                col_no = sp[0]
            else:
                col_no += 1
                ref = f"{idx_to_col(col_no)}{row_no}"
            if col_no > max_cols:
                raise BudgetExceeded("columns", max_cols)
            t = el.get("t", "n")
            v = f = is_ = None
            has_formula = False
            for ch in el:
                cn = _ln(ch.tag)
                if cn == "v":
                    v = ch.text or ""
                elif cn == "f":
                    f, has_formula = ch.text or "", True
                elif cn == "is":
                    is_ = _text(ch)
            kind, text = "number", None
            if t == "s":
                try:
                    text, kind = shared[int(v)], "text"
                except (ValueError, IndexError, TypeError):
                    raise Tab006Malformed("bad shared string index") from None
            elif t == "inlineStr":
                text, kind = (is_ or ""), "text"
            elif t == "str":
                text, kind = (v or ""), "text"
            elif t == "b":
                text, kind = ("TRUE" if v == "1" else "FALSE"), "bool"
            elif t == "e":
                text, kind = (v or ""), "error"
            elif v:
                text = v
                xf = el.get("s", "")
                dk = date_xf.get(int(xf)) if xf.isdigit() else None
                iso = _iso(v, dk, date1904) if dk else None
                if iso:
                    text, kind = iso, "date"
            if not text:
                if has_formula and f:
                    text, kind = "=" + f, "text"  # no cached value: the expression is kept as data
                else:
                    el.clear()
                    continue
            ncells += 1
            if ncells > max_cells:
                raise BudgetExceeded("cells", max_cells)
            xs = el.get("s", "")
            cells.append({"ref": ref, "text": text, "kind": kind, "formula": has_formula, "hidden": row_reason,
                          "style": hide_xf.get(int(xs), "") if xs.isdigit() else ""})
            el.clear()
    for c in cells:
        cno = split_ref(c["ref"])[0]
        creason = next((r for a, b, r in cols_hidden if a <= cno <= b), "")
        if creason:
            hidden_cols.add(cno)
        c["hidden"] = c["hidden"] or creason or c.pop("style")
        c.pop("style", None)
    rows_seen = {}
    for c in cells:
        if not c["hidden"]:
            rows_seen.setdefault(split_ref(c["ref"])[1], []).append((c["text"], c["kind"]))
    return {"type": "sheet", "name": name, "state": state, "encoding": "", "delimiter": "",
            "header_row": detect_header_row(rows_seen), "cells": cells, "comments": [],
            "hidden_rows": _ranges(hidden_rows),
            "hidden_cols": [idx_to_col(c) for c in sorted(hidden_cols)[:MAX_LIST]]}


def read_xlsx(data: bytes, budget: Budget, max_rows: int, max_cols: int, max_cells: int,
              max_sheets: int) -> list:
    pkg = Package(data, budget)
    if not pkg.has("[Content_Types].xml") or not pkg.has("xl/workbook.xml"):
        raise Tab001UnsupportedFormat("not an OOXML spreadsheet (.xlsx)")
    ct = pkg.read("[Content_Types].xml")
    check_xml_bytes(ct)
    ctl = ct.lower()
    if b"macroenabled" in ctl or b"vbaproject" in ctl:
        raise Tab005MacroRefused("macro-enabled workbook")
    if b"encryptedpackage" in ctl:
        raise Tab002Encrypted("encrypted package")
    external = any(n.startswith("xl/externalLinks/") for n in pkg.names)
    wb_rels = {rid: (typ, tgt, ext) for rid, typ, tgt, ext in _rels(pkg, "xl/workbook.xml")}
    external = external or any(e or t == "externalLink" for t, _, e in wb_rels.values())
    shared = _shared(pkg)
    date_xf, hide_xf = _styles(pkg)
    sheets, names, date1904 = [], [], False
    root = parse_small(pkg.read("xl/workbook.xml"), pkg.budget)
    for ch in root:
        n = _ln(ch.tag)
        if n == "workbookPr":
            date1904 = ch.get("date1904", "") in ("1", "true")
        elif n == "sheets":
            for s in ch:
                rid = next((v for k, v in s.attrib.items() if _ln(k) == "id"), "")
                sheets.append((s.get("name", ""), s.get("state", "visible"), rid))
        elif n == "definedNames":
            for d in ch:
                if len(d.get("name", "")) > MAX_DEFINED_NAME:
                    raise Tab006Malformed("defined name longer than 255 characters")
                names.append({"name": d.get("name", ""), "text": d.text or "",
                              "hidden": d.get("hidden", "") in ("1", "true")})
    if len(sheets) > max_sheets:
        raise BudgetExceeded("sheets", max_sheets)
    out = [{"type": "workbook", "names": names, "external_links": external, "date1904": date1904}]
    for idx, (name, state, rid) in enumerate(sheets, start=1):
        if len(name) > MAX_SHEET_NAME:
            raise Tab006Malformed("sheet name longer than 31 characters")
        rel = wb_rels.get(rid)
        if not rel or rel[2] or rel[1] not in pkg.names:
            raise Tab006Malformed("sheet relationship missing")
        sh = _sheet(pkg, rel[1], name, state if state in ("visible", "hidden", "veryHidden") else "hidden",
                    shared, date_xf, hide_xf, date1904, max_rows, max_cols, max_cells)
        sh["index"], sh["locator"] = idx, f"s{idx}"  # structured locator: a name never goes in a path
        sheet_rels = _rels(pkg, rel[1])
        sh["external_links"] = any(e for _, _, _, e in sheet_rels)
        for _, typ, tgt, ext in sheet_rels:
            if not ext and typ in ("comments", "threadedComment") and tgt in pkg.names:
                sh["comments"].extend(_comments(pkg, tgt))
        out.append(sh)
    return out
