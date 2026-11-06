#!/usr/bin/env python3
"""Outline the wordmark from Alexandria SemiBold (wght 600). Used by build_logo.py and build_logo_proposed.py.
Needs fontTools (only when ORRERY_FONT_ALEXANDRIA is set). The font file is NOT in the repo: point the env var at Alexandria-VF.ttf
(source https://github.com/Gue3bara/Alexandria, SIL OFL 1.1). Returns None when the variable is unset or unusable, so callers fall back to the placeholder."""
import os

ENV = "ORRERY_FONT_ALEXANDRIA"
WGHT = 600
TRACKING = -0.005   # of em

def font_path():
    p = os.environ.get(ENV)
    return p if p and os.path.isfile(p) else None

def _kern_pairs(font, glyph_names):
    """Simple GPOS 'kern' pair lookup (PairPos formats 1 and 2, incl. Extension). Returns {(left, right): xAdvance units}."""
    gpos = font["GPOS"].table if "GPOS" in font else None
    if gpos is None:
        return {}
    idx = set()
    for fr in gpos.FeatureList.FeatureRecord:
        if fr.FeatureTag == "kern":
            idx.update(fr.Feature.LookupListIndex)
    res = {}
    for li in sorted(idx):
        lk = gpos.LookupList.Lookup[li]
        for st in lk.SubTable:
            if lk.LookupType == 9:
                st = st.ExtSubTable
            if lk.LookupType not in (2, 9) or not hasattr(st, "Class1Record") and not hasattr(st, "PairSet"):
                continue
            cov = st.Coverage.glyphs
            for a, b in zip(glyph_names, glyph_names[1:]):
                if (a, b) in res or a not in cov:
                    continue
                if st.Format == 1:
                    ps = st.PairSet[cov.index(a)]
                    for pvr in ps.PairValueRecord:
                        if pvr.SecondGlyph == b and pvr.Value1 is not None:
                            res[(a, b)] = getattr(pvr.Value1, "XAdvance", 0) or 0
                elif st.Format == 2:
                    c1 = st.ClassDef1.classDefs.get(a, 0)
                    c2 = st.ClassDef2.classDefs.get(b, 0)
                    v = st.Class1Record[c1].Class2Record[c2].Value1
                    if v is not None and (getattr(v, "XAdvance", 0) or 0):
                        res[(a, b)] = v.XAdvance
    return res

def build(name, scale_to_cap=None):
    """Returns dict: glyph outlines laid out in font units (y up), or None. Call path_data() to place them."""
    fp = font_path()
    if not fp:
        return None
    from fontTools.ttLib import TTFont
    from fontTools.varLib import instancer
    # Note: kern values come from the instanced font (variations applied by the instancer).
    inst = instancer.instantiateVariableFont(TTFont(fp), {"wght": WGHT})
    upm = inst["head"].unitsPerEm
    cmap = inst.getBestCmap()
    gnames = [cmap[ord(c)] for c in name]
    kern = _kern_pairs(inst, gnames)
    gs = inst.getGlyphSet()
    hmtx = inst["hmtx"]
    pen_x, items = 0.0, []
    for i, g in enumerate(gnames):
        items.append((g, pen_x))
        adv = hmtx[g][0]
        k = kern.get((g, gnames[i + 1]), 0) if i + 1 < len(gnames) else 0
        pen_x += adv + k + (TRACKING * upm if i + 1 < len(gnames) else 0)
    from fontTools.pens.boundsPen import BoundsPen
    from fontTools.pens.transformPen import TransformPen
    bp = BoundsPen(gs)
    for g, x in items:
        gs[g].draw(TransformPen(bp, (1, 0, 0, 1, x, 0)))
    cap = inst["OS/2"].sCapHeight
    return dict(glyphset=gs, items=items, upm=upm, cap=cap, bounds=bp.bounds, advance=pen_x, kern=kern, names=gnames, font=inst)

def path_data(w, s, ox, oy):
    """SVG path for the laid-out wordmark. s = svg units per font unit; (ox, oy) = svg position of the origin (baseline, pen start).
    y is flipped. Coordinates rounded to 3 decimals."""
    from fontTools.pens.svgPathPen import SVGPathPen
    from fontTools.pens.transformPen import TransformPen
    sp = SVGPathPen(w["glyphset"], ntos=lambda v: f"{v:.3f}".rstrip("0").rstrip(".") or "0")
    for g, x in w["items"]:
        w["glyphset"][g].draw(TransformPen(sp, (s, 0, 0, -s, ox + x * s, oy)))
    return sp.getCommands()
