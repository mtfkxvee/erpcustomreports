# Copyright (c) 2026, X-SHA and contributors
# For license information, please see license.txt
#
# Laporan "Weekly Margin" (Target vs Achievement) - tampilan ERP dari file
# "WEEKLY MARGIN AGUSTUS 2026" bagian "WEEKLY MARGIN CLEAR X-SHA GROUP" (susunan
# baris & kolom mengikuti file), rumus = API sales_api.get_weekly_margin
# (_margin_row). Minggu = Senin-Minggu.
#  - Sales Achv (include promo) = Sales-Retur + Promo + Rafaksi, mengikuti file
#    terbaru "WEEKLY MARGIN CLEAR 5-11 OCT" (P = O + H + I) & API; kolom
#    "Promo-X + Rafaksi" = selisih Sales Achv - Sales (exclude promo).
#  - Target margin = dokumen resmi "TARGET SALES UNIT BISNIS BARU" sheet RESUME
#    TARGET MARGIN Semester II (sales_api._MARGIN_TARGET_PCT); baris gabungan
#    (Cikiray All dst) pakai target outlet offline-nya, Total dept pakai target
#    dept, TOTAL pakai target HO bulanan.
#  - Jurnal potongan & HPP outlet dibaca dari snapshot harian (sales_snapshot)
#    kalau minggu itu lengkap, kalau tidak live + label "(live)".
#  - Kemitraan & MBG: sales + HPP dari input manual "Kemitraan MBG Sales History"
#    (field HPP); kalau HPP blm diinput, margin dikosongkan & tdk ikut TOTAL.

import frappe
from frappe import _
from frappe.utils import formatdate, getdate, today

from custom_reports.sales_api import (
    _GL_MARGIN_ACCOUNTS,
    _MARGIN_DEPT_TARGET_PCT,
    _MARGIN_TARGET_PCT,
    _OUTLET_COST_CENTER,
    _gl_deductions_by_outlet,
    _hpp_by_outlet,
    _margin_row,
    _monday_week_bounds,
)
from custom_reports.sales_snapshot import load_margin

# Target margin HO per bulan, Semester II 2026 (RESUME TARGET MARGIN, kolom E)
_HO_TARGET_BY_MONTH = {7: 0.20858447488584475, 8: 0.20804878048780487, 9: 0.20626506024096386,
                       10: 0.2065871121718377, 11: 0.20738041002277904, 12: 0.20793388429752066}

# (kode / daftar kode, label, no, target_dari)
_FASHION = [
    ("XSC", "Cikiray offline", None), ("XSC-OL", "Online Cikiray", None), (["XSC", "XSC-OL"], "Cikiray All", 1),
    ("PSR", "Pasar", 2), ("XPY", "Panyingkiran", 3), ("XJB", "Furniture", 4),
    ("XCW", "Ciawi offline", None), ("OCW", "Online Ciawi", None), (["XCW", "OCW"], "Ciawi All", 5),
    ("XSP", "SP Fashion offline", None), ("XSP-OL", "Online SP Fashion", None), (["XSP", "XSP-OL"], "SP Fashion All", 6),
    ("HCW", "X-sha Rumah Kedua", 7),
]
_FMCG = [
    ("XSM", "Supermart", None), ("XSMGROW", "XSM Grow", None), (["XSM", "XSMGROW"], "Supermart All", 1),
    ("XMJ", "X-Shamart Mangunreja", 2), ("XWP", "X-Shamart Warung Peuteuy", 3), ("XPH", "X-Shamart Puspahiang", 4),
    ("XTJ", "X-Shamart Tanjung jaya", 5), ("XCR", "X-Shamart Cisaruni", 6), ("TASMU", "Tasmu Mart", 7),
    ("MNR", "Menara X-Shamart", 8), ("UIN", "UIN Grow", 9),
]


def _flat(items):
    out = []
    for code, _label, _no in items:
        if isinstance(code, str):
            out.append(code)
    return out


def _kmt_mbg_sales_hpp(start, end):
    """{KMT|MBG: {"sales", "hpp", "hpp_filled"}} dari Kemitraan MBG Sales History
    (sub_kode SKM selalu di-exclude - rollup/duplikat, lihat sales_api)."""
    rows = frappe.db.sql("""
        SELECT kategori, SUM(nominal) AS sales, SUM(COALESCE(hpp, 0)) AS hpp,
               SUM(CASE WHEN COALESCE(hpp, 0) <> 0 THEN 1 ELSE 0 END) AS n_hpp
        FROM `tabKemitraan MBG Sales History`
        WHERE tanggal BETWEEN %s AND %s AND sub_kode != 'SKM'
        GROUP BY kategori
    """, (start, end), as_dict=True)
    mapping = {"Kemitraan": "KMT", "MBG": "MBG"}
    return {mapping[r.kategori]: {"sales": r.sales or 0, "hpp": r.hpp or 0, "hpp_filled": bool(r.n_hpp)}
            for r in rows if r.kategori in mapping}


def execute(filters=None):
    filters = filters or {}
    as_of = getdate(filters.get("tanggal") or today())
    week_start, week_end = _monday_week_bounds(as_of)
    week_start, week_end = getdate(week_start), getdate(week_end)

    outlets = list(_OUTLET_COST_CENTER)
    snap = load_margin(week_start, week_end)
    is_live = snap is None
    if is_live:
        gl_data = _gl_deductions_by_outlet(week_start, week_end, outlets)
        hpp_data = _hpp_by_outlet(week_start, week_end, outlets)
    else:
        gl_data, hpp_data = snap
    manual = _kmt_mbg_sales_hpp(week_start, week_end)

    def gl_sum(codes):
        return {acc: sum(gl_data.get(o, {}).get(acc, 0) or 0 for o in codes) for acc in _GL_MARGIN_ACCOUNTS}

    def build(label, codes, target, no=None, bold=0):
        m = _margin_row(label, label, gl_sum(codes), sum(hpp_data.get(o, 0) or 0 for o in codes), target_pct=target)
        return _row(m, label, target, no, bold)

    def manual_row(code, label):
        d = manual.get(code, {"sales": 0, "hpp": 0, "hpp_filled": False})
        target = _MARGIN_TARGET_PCT.get(code)
        if not d["hpp_filled"]:
            return {"no": None, "outlet": label, "sales_retur": d["sales"], "sales_achv": d["sales"],
                    "target": target * 100 if target else None, "_sales": d["sales"], "_margin": None,
                    "_note": "HPP blm diinput"}
        margin = d["sales"] - d["hpp"]
        pct = margin / d["sales"] if d["sales"] else None
        return {"no": None, "outlet": label, "deal_margin_clear": margin, "sales_retur": d["sales"],
                "margin_pct": pct * 100 if pct is not None else None, "promo_x": 0,
                "deal_margin_plus": margin, "sales_achv": d["sales"],
                "margin_pct_incl": pct * 100 if pct is not None else None,
                "target": target * 100 if target else None,
                "achv": (pct / target * 100) if (pct is not None and target) else None,
                "_sales": d["sales"], "_margin": margin}

    data = []
    for section, items, dept_key in (("FASHION & H.S", _FASHION, "FASHION"), ("FMCG", _FMCG, "FMCG")):
        data.append({"outlet": section, "bold": 1, "is_header": 1})
        for code, label, no in items:
            codes = code if isinstance(code, list) else [code]
            target = _MARGIN_TARGET_PCT.get(codes[0])  # baris gabungan: target outlet offline
            data.append(build(label, codes, target, no, bold=1 if isinstance(code, list) else 0))
        data.append(build("Total", _flat(items), _MARGIN_DEPT_TARGET_PCT.get(dept_key), bold=1))

    xsl = build("Mini Soccer", ["XSL"], _MARGIN_TARGET_PCT.get("XSL"))
    kmt = manual_row("KMT", "X-Sha Kemitraan")
    mbg = manual_row("MBG", "MBG (Dapur)")
    data += [{"outlet": "HO", "bold": 1, "is_header": 1}, kmt, xsl, mbg]

    # TOTAL = Fashion + FMCG + Mini Soccer + (KMT/MBG yg HPP-nya sudah diinput)
    si_codes = _flat(_FASHION) + _flat(_FMCG) + ["XSL"]
    m = _margin_row("TOTAL", "TOTAL", gl_sum(si_codes), sum(hpp_data.get(o, 0) or 0 for o in si_codes))
    clear, sales_r = m["deal_margin_clear"], m["sales_retur"]
    plus, achv_sales = m["deal_margin_plus"], m["sales_achv"]
    excluded = []
    for r in (kmt, mbg):
        if r["_margin"] is None:
            excluded.append(r["outlet"])
            continue
        clear += r["_margin"]; plus += r["_margin"]; sales_r += r["_sales"]; achv_sales += r["_sales"]
    ho_target = _HO_TARGET_BY_MONTH.get(as_of.month) if as_of.year == 2026 else None
    pct_incl = plus / achv_sales if achv_sales else None
    data.append({
        "outlet": "TOTAL", "bold": 1, "deal_margin_clear": clear, "sales_retur": sales_r,
        "margin_pct": clear / sales_r * 100 if sales_r else None, "promo_x": achv_sales - sales_r,
        "deal_margin_plus": plus, "sales_achv": achv_sales,
        "margin_pct_incl": pct_incl * 100 if pct_incl is not None else None,
        "target": ho_target * 100 if ho_target else None,
        "achv": pct_incl / ho_target * 100 if (pct_incl is not None and ho_target) else None,
    })

    for r in data:
        for k in [k for k in r if k.startswith("_")]:
            r.pop(k)
        for k in ("deal_margin_clear", "sales_retur", "promo_x", "deal_margin_plus", "sales_achv"):
            if r.get(k) is not None:
                r[k] = round(r[k])
        for k in ("margin_pct", "margin_pct_incl", "target", "achv"):
            if r.get(k) is not None:
                r[k] = round(r[k], 2)

    info = f"Periode: {formatdate(week_start, 'dd')}-{formatdate(week_end, 'dd MMMM yyyy')} (Senin-Minggu)"
    if is_live:
        info += "  |  (live)"
    if excluded:
        info += f"  |  {', '.join(excluded)}: HPP blm diinput -> margin kosong & tdk ikut TOTAL"
    data.insert(0, {"outlet": info, "bold": 1, "is_info": 1})
    return get_columns(), data


def _row(m, label, target, no, bold):
    achv_sales, sales_r = m["sales_achv"] or 0, m["sales_retur"] or 0
    return {
        "no": no, "outlet": label, "bold": bold,
        "deal_margin_clear": m["deal_margin_clear"], "sales_retur": m["sales_retur"], "margin_pct": m["margin_pct"],
        "promo_x": achv_sales - sales_r, "deal_margin_plus": m["deal_margin_plus"], "sales_achv": m["sales_achv"],
        "margin_pct_incl": m["margin_pct_incl"], "target": target * 100 if target else None, "achv": m["achv_pct"],
    }


def get_columns():
    def col(fieldname, label, fieldtype="Int", width=130):
        return {"fieldname": fieldname, "label": label, "fieldtype": fieldtype, "width": width}
    return [
        col("no", _("No"), "Data", 45),
        col("outlet", _("Outlet"), "Data", 220),
        col("deal_margin_clear", _("Exclude Promo: Deal Margin")),
        col("sales_retur", _("Exclude Promo: Sales Achv"), width=140),
        col("margin_pct", _("Exclude Promo: Margin"), "Percent", 110),
        col("promo_x", _("Promo-X + Rafaksi")),
        col("deal_margin_plus", _("Include Promo: Deal Margin")),
        col("sales_achv", _("Include Promo: Sales Achv"), width=140),
        col("margin_pct_incl", _("Include Promo: Margin"), "Percent", 110),
        col("target", _("Target"), "Percent", 90),
        col("achv", _("ACHV"), "Percent", 90),
    ]
