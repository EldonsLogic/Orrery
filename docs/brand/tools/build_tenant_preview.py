#!/usr/bin/env python3
"""Generate ../preview-tenant-themes.html (one static file, no external scripts) from derive_tenant_theme.derive().
Run through: python3 tools/derive_tenant_theme.py --preview preview-tenant-themes.html   (path relative to docs/brand)"""
import html, pathlib
import themelib as T
import derive_tenant_theme as D

TENANTS = [  # fictional; names and colours invented
    ("al-nakhla", "Al Nakhla Trading", "النخلة للتجارة", "#0F766E", None),
    ("desert-rose", "Desert Rose Foods", "ورد الصحراء للأغذية", "#7E22CE", "#B45309"),
    ("gulf-harbour", "Gulf Harbour Logistics", "الخليج هاربر للشحن", "#1F3A8A", None),
    ("sahab", "Sahab Hardware", "سحاب للأدوات", "#B45309", None),
    ("wahat", "Wahat Pharma", "واحات للأدوية", "#006C35", "#F59E0B"),
    ("mawj", "Mawj Textiles", "موج للمنسوجات", "#0E7490", None),
]
REJECTED = ("Shams Bakery", "مخبز شمس", "#FFD400", None)
LOWER = "M5 27L27.5 27A22.5 22.5 0 0 0 22.236 12.537Z"
UPPER = "M5 27L18.852 9.27A22.5 22.5 0 0 0 5 4.5Z"
MARK = f'<svg class="mk" viewBox="4 3.5 24.5 24.5" aria-hidden="true"><path d="{LOWER}"/><path d="{UPPER}"/></svg>'
ICON = {  # Lucide-style outline paths, 24 px, 1.75 stroke (drawn here as stand-ins)
    "check": '<path d="M20 6 9 17l-5-5"/>', "alert": '<path d="m10.3 3.9-8.4 14.5A2 2 0 0 0 3.6 21h16.8a2 2 0 0 0 1.7-2.6L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4M12 17h.01"/>',
    "x": '<path d="M18 6 6 18M6 6l12 12"/>'}
def ico(n):
    return f'<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{ICON[n]}</svg>'
def e(s):
    return html.escape(s)

def logo(init, name_en, name_ar):
    return (f'<span class="lg"><span class="lgs" aria-hidden="true">{e(init)}</span>'
            f'<span class="en">{e(name_en)}</span><span class="ar" lang="ar">{e(name_ar)}</span></span>')

def panel(cls, mode, name_en, name_ar, init, res):
    return f'''<div class="pn {cls}" data-mode="{mode}">
<div class="ph">{logo(init, name_en, name_ar)}<span class="tag">{mode}</span></div>
<div class="row"><button class="b1" type="button"><span class="en">Approve invoice</span><span class="ar" lang="ar">اعتماد الفاتورة</span></button>
<button class="b2" type="button"><span class="en">Reject</span><span class="ar" lang="ar">رفض</span></button></div>
<div class="row"><span class="pill s">{ico("check")}<span class="en">Reported</span><span class="ar" lang="ar">تم الإبلاغ</span></span>
<span class="pill w">{ico("alert")}<span class="en">Needs review</span><span class="ar" lang="ar">يحتاج مراجعة</span></span>
<span class="pill d">{ico("x")}<span class="en">Rejected</span><span class="ar" lang="ar">مرفوضة</span></span></div>
<div class="chat"><div class="am">{MARK}<p><span class="en">Done. 4 invoices are ready. Post them to the ledger?</span><span class="ar" lang="ar">تمّ. 4 فواتير جاهزة. هل أرحّلها إلى دفتر الأستاذ؟</span></p></div>
<div class="um"><span class="en">Yes, post them.</span><span class="ar" lang="ar">نعم، رحّلها.</span></div></div>
<table><tr><th><span class="en">Invoice</span><span class="ar" lang="ar">الفاتورة</span></th><th class="n"><span class="en">Amount</span><span class="ar" lang="ar">المبلغ</span></th></tr>
<tr class="sel"><td>INV-0418</td><td class="n"><bdi dir="ltr">12,480.00</bdi> <span class="cur"><span class="en">SAR</span><span class="ar" lang="ar">ر.س</span></span></td></tr>
<tr><td>INV-0419</td><td class="n"><bdi dir="ltr">3,015.50</bdi> <span class="cur"><span class="en">SAR</span><span class="ar" lang="ar">ر.س</span></span></td></tr></table>
<div class="sheet"><div class="ih">{logo(init, name_en, name_ar)}<span class="doc"><span class="en">Tax invoice</span><span class="ar" lang="ar">فاتورة ضريبية</span><br><bdi dir="ltr">INV-0418 · 6 Nov 2026</bdi></span></div>
<div class="qr"><span>QR</span></div><div class="rule"></div></div>
<p class="cap">primary <b>{res[mode]["primary"]}</b> · label <b>{res[mode]["primaryLabel"]}</b> · accent <b>{res[mode]["accent"]}</b></p>
</div>'''

CSS = '''*{box-sizing:border-box}body{margin:0;font:14px/20px system-ui,sans-serif;background:#F3F4F6;color:#12151B}
html[dir=rtl] body{line-height:24px}main{max-width:1200px;margin:0 auto;padding:16px}
h1{font-size:24px;line-height:32px;margin:8px 0}h2{font-size:16px;line-height:24px;margin:0}
.note{max-width:72ch;margin:0 0 16px;color:#54575B}.bar{display:flex;gap:8px;align-items:center;margin-bottom:16px;flex-wrap:wrap}
.bar button{font:inherit;height:40px;padding:0 16px;border-radius:8px;border:1px solid rgba(36,67,208,.4);background:#fff;color:#2443D0;cursor:pointer}
.bar button:focus-visible{outline:2px solid #2443D0;outline-offset:2px}
.ar{display:none}html[dir=rtl] .ar{display:inline}html[dir=rtl] .en{display:none}
.tn{background:#fff;border:1px solid #E3E3E4;border-radius:12px;padding:16px;margin-bottom:16px}
.tn header{display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap;margin-bottom:12px}.tn header span{color:#54575B}
.pair{display:grid;grid-template-columns:1fr 1fr;gap:16px}@media(max-width:760px){.pair{grid-template-columns:1fr}}
.pn{background:var(--color-background);color:var(--color-text);border-radius:12px;padding:16px;border:1px solid var(--color-border);min-width:0}
.ph{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px}.tag{font-size:12px;line-height:16px;color:var(--color-text-muted)}
.lg{display:inline-flex;align-items:center;gap:8px;font-weight:600}.lgs{display:inline-grid;place-items:center;width:24px;height:24px;background:var(--color-primary);color:var(--color-primary-label);border-radius:4px;font-size:12px}
.row{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px}
.b1,.b2{font:inherit;font-weight:500;height:40px;padding:0 16px;border-radius:8px;cursor:pointer}
.b1{background:var(--color-primary);color:var(--color-primary-label);border:1px solid var(--color-primary)}.b1:hover{background:var(--color-primary-hover)}.b1:active{background:var(--color-primary-pressed)}
.b2{background:transparent;color:var(--color-primary);border:1px solid color-mix(in srgb,var(--color-primary) 40%,transparent)}.b2:hover{background:var(--state-secondary-hover)}
.b1:focus-visible,.b2:focus-visible{outline:2px solid var(--color-primary);outline-offset:2px}
.pill{display:inline-flex;gap:4px;align-items:center;height:24px;padding:0 8px;border-radius:12px;font-size:12px;font-weight:500}.ic{width:16px;height:16px;flex:none}
.pill.s{background:var(--color-success-tint);color:var(--color-success-pill)}.pill.s .ic{color:var(--color-success)}
.pill.w{background:var(--color-warning-tint);color:var(--color-warning-pill)}.pill.w .ic{color:var(--color-warning)}
.pill.d{background:var(--color-danger-tint);color:var(--color-danger-pill)}.pill.d .ic{color:var(--color-danger)}
.chat{display:grid;gap:8px;margin-bottom:12px}.am{display:flex;gap:8px;align-items:flex-start;background:var(--color-surface);border:1px solid var(--color-border);border-radius:12px;padding:12px}
.am p{margin:0}.mk{width:24px;height:24px;flex:none;fill:var(--color-primary)}
.um{justify-self:end;background:var(--state-selected);border-radius:12px;padding:8px 12px;max-width:80%}
table{width:100%;border-collapse:collapse;background:var(--color-surface);border:1px solid var(--color-border);margin-bottom:12px}
th,td{padding:8px 12px;text-align:start;border-bottom:1px solid var(--color-border)}th{font-weight:500;color:var(--color-text-muted)}
.n{text-align:end;font-variant-numeric:tabular-nums}.cur{color:var(--color-text-muted)}tr.sel td{background:var(--state-selected)}tr.sel td:first-child{box-shadow:inset 2px 0 0 var(--color-primary)}
html[dir=rtl] tr.sel td:first-child{box-shadow:inset -2px 0 0 var(--color-primary)}
.sheet{background:#fff;color:#12151B;border:1px solid #E3E3E4;border-radius:4px;padding:12px;margin-bottom:8px;display:grid;gap:8px;grid-template-columns:1fr auto}
.sheet .lgs{background:var(--sheet-primary);color:var(--sheet-label)}.ih{grid-column:1/-1;display:flex;justify-content:space-between;gap:8px;align-items:flex-start}.doc{text-align:end;font-size:12px;line-height:16px}
.qr{width:64px;height:64px;border:1px dashed #54575B;display:grid;place-items:center;font-size:12px;color:#54575B;grid-column:2}.rule{height:2px;background:var(--sheet-accent);align-self:end;grid-column:1;grid-row:2}
.cap{font-size:12px;line-height:16px;color:var(--color-text-muted);margin:0}.cap b{font-weight:500;color:var(--color-text)}
.rej{border-color:#C21F3A}.sw{display:inline-block;width:24px;height:24px;border-radius:4px;vertical-align:middle;border:1px solid #E3E3E4}
.rej p{margin:8px 0;max-width:80ch}'''

def build(out_path):
    out = pathlib.Path(out_path)
    if not out.is_absolute():
        out = T.ROOT / out_path
    css_vars, blocks = [], []
    for i, (slug, en, ar, pr, ac) in enumerate(TENANTS):
        res = D.derive(pr, ac)
        assert res["status"] == "ok", (en, res["reasons"])
        for m in ("light", "dark"):
            v = "".join(f"{k}:{val};" for k, val in res[m]["vars"].items())
            lv = res["light"]
            v += f"--sheet-primary:{lv['primary']};--sheet-label:{lv['primaryLabel']};--sheet-accent:{lv['accent']};"
            css_vars.append(f".t{i}-{m}{{{v}}}")
        init = en[0]
        adj = "; ".join(res["adjustments"]) or "no adjustment"
        blocks.append(f'''<section class="tn" id="{slug}"><header><h2>{e(en)} <span lang="ar">· {e(ar)}</span></h2><span>input {pr}{" + accent " + ac if ac else ""} → accepted</span></header>
<div class="pair">{panel(f"t{i}-light", "light", en, ar, init, res)}{panel(f"t{i}-dark", "dark", en, ar, init, res)}</div>
<p class="cap">{e(adj)}{" · warning: " + e(res["warnings"][0]) if res["warnings"] else ""}</p></section>''')
    ren, rar, rp, ra = REJECTED
    rr = D.derive(rp, ra)
    assert rr["status"] == "rejected"
    rej = f'''<section class="tn rej" id="rejected"><header><h2>{e(ren)} <span lang="ar">· {e(rar)}</span></h2><span>input {rp} → <b>rejected</b></span></header>
<p><span class="sw" style="background:{rp}"></span> {rp}</p><p>{e(rr["reasons"][0])}</p><p class="cap">Nothing is applied. The owner sees this message, the colour stays unchanged, and the audit log records the attempt.</p></section>'''
    page = f'''<!doctype html>
<html lang="en" dir="ltr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Tenant themes (PROPOSED, v1.1)</title><style>{CSS}{"".join(css_vars)}</style></head><body><main>
<h1>Tenant themes: PROPOSED</h1>
<p class="note">Fictional tenants, invented names and colours; the logo is a text and shape stand-in. Each tenant is one chosen colour; light and dark are derived by <code>tools/derive_tenant_theme.py</code> and every pair passes AA (see 12-tenant-theming.md). The invoice sheet is always light (documents are printed). Arabic strings are unreviewed (native review required). Fonts are not loaded in this preview.</p>
<div class="bar"><button type="button" id="dir" aria-pressed="false">LTR / RTL</button><span>Generated file. Do not edit; rerun the script.</span></div>
{"".join(blocks)}{rej}
</main><script>document.getElementById("dir").addEventListener("click",function(){{var d=document.documentElement;var r=d.dir!=="rtl";d.dir=r?"rtl":"ltr";d.lang=r?"ar":"en";this.setAttribute("aria-pressed",r)}})</script>
</body></html>
'''
    out.write_text(page, encoding="utf-8")
    return out

if __name__ == "__main__":
    print(build("preview-tenant-themes.html"))
