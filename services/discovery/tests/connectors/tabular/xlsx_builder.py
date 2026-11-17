"""Test-only: build small synthetic .xlsx zips in memory. Synthetic data only."""
import io
import zipfile
from xml.sax.saxutils import escape

NS = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
RNS = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
XML = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'


def col(i):
    s = ""
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def build(sheets, names=(), extra=None, content_types_extra="", wb_extra="", doctype="", compress=zipfile.ZIP_DEFLATED,
          date1904=False, custom_fmt="dd/mm/yyyy hh:mm"):
    """sheets: [{name, state, rows, hidden_rows, hidden_cols, comments}]. Cell values: str (shared),
    int/float (number), ("inline", s), ("f", formula, cached), ("date", serial), ("dt", serial), ("time", serial)."""
    shared, sidx = [], {}

    def sst(s):
        if s not in sidx:
            sidx[s] = len(shared)
            shared.append(s)
        return sidx[s]

    parts, wb_sheets, wb_rels, ct = {}, [], [], ""
    for n, sh in enumerate(sheets, start=1):
        rows_xml = []
        for r, row in enumerate(sh["rows"], start=1):
            cells = []
            for c, v in enumerate(row, start=1):
                if v is None:
                    continue
                ref = f"{col(c)}{r}"
                if isinstance(v, str):
                    cells.append(f'<c r="{ref}" t="s"><v>{sst(v)}</v></c>')
                elif isinstance(v, (int, float)):
                    cells.append(f'<c r="{ref}"><v>{v}</v></c>')
                elif v[0] == "inline":
                    cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{escape(v[1])}</t></is></c>')
                elif v[0] == "f":
                    cv = v[2]
                    if isinstance(cv, str):
                        cells.append(f'<c r="{ref}" t="str"><f>{escape(v[1])}</f><v>{escape(cv)}</v></c>')
                    else:
                        cells.append(f'<c r="{ref}"><f>{escape(v[1])}</f><v>{cv}</v></c>')
                else:
                    style = {"date": 1, "dt": 2, "time": 3}[v[0]]
                    cells.append(f'<c r="{ref}" s="{style}"><v>{v[1]}</v></c>')
            hid = ' hidden="1"' if r in sh.get("hidden_rows", ()) else ""
            rows_xml.append(f'<row r="{r}"{hid}>{"".join(cells)}</row>')
        cols = "".join(f'<col min="{c}" max="{c}" width="9" hidden="1"/>' for c in sh.get("hidden_cols", ()))
        cols = f"<cols>{cols}</cols>" if cols else ""
        parts[f"xl/worksheets/sheet{n}.xml"] = (
            f'{XML}<worksheet {NS}>{cols}<sheetData>{"".join(rows_xml)}</sheetData></worksheet>')
        ct += f'<Override PartName="/xl/worksheets/sheet{n}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        wb_rels.append(f'<Relationship Id="rId{n}" Type="{REL}/worksheet" Target="worksheets/sheet{n}.xml"/>')
        st = sh.get("state", "visible")
        stx = "" if st == "visible" else f' state="{st}"'
        wb_sheets.append(f'<sheet name="{escape(sh["name"])}" sheetId="{n}"{stx} r:id="rId{n}"/>')
        if sh.get("comments"):
            cm = "".join(f'<comment ref="{ref}" authorId="0"><text><r><t>{escape(t)}</t></r></text></comment>'
                         for ref, t in sh["comments"].items())
            parts[f"xl/comments{n}.xml"] = f'{XML}<comments {NS}><authors><author>a</author></authors><commentList>{cm}</commentList></comments>'
            parts[f"xl/worksheets/_rels/sheet{n}.xml.rels"] = (
                f'{XML}<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                f'<Relationship Id="rId1" Type="{REL}/comments" Target="../comments{n}.xml"/></Relationships>')
    dn = "".join(f'<definedName name="{escape(a)}">{escape(b)}</definedName>' for a, b in names)
    dn = f"<definedNames>{dn}</definedNames>" if dn else ""
    pr = '<workbookPr date1904="1"/>' if date1904 else ""
    parts["xl/workbook.xml"] = (f'{XML}{doctype}<workbook {NS} {RNS}>{pr}<sheets>{"".join(wb_sheets)}</sheets>{dn}{wb_extra}</workbook>')
    parts["xl/_rels/workbook.xml.rels"] = (
        f'{XML}<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{"".join(wb_rels)}</Relationships>')
    sis = "".join(f"<si><t>{escape(s)}</t></si>" for s in shared)
    parts["xl/sharedStrings.xml"] = f'{XML}<sst {NS}>{sis}</sst>'
    parts["xl/styles.xml"] = (
        f'{XML}<styleSheet {NS}><numFmts count="1"><numFmt numFmtId="164" formatCode="{custom_fmt}"/></numFmts>'
        '<cellXfs><xf numFmtId="0"/><xf numFmtId="14"/><xf numFmtId="164"/><xf numFmtId="21"/></cellXfs></styleSheet>')
    parts["[Content_Types].xml"] = (
        f'{XML}<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        f'{ct}{content_types_extra}</Types>')
    parts["_rels/.rels"] = (f'{XML}<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                            f'<Relationship Id="rId1" Type="{REL}/officeDocument" Target="xl/workbook.xml"/></Relationships>')
    for k, v in (extra or {}).items():
        if v is None:
            parts.pop(k, None)
        else:
            parts[k] = v
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compress) as z:
        for k, v in parts.items():
            z.writestr(k, v)
    return buf.getvalue()
